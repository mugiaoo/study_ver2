#!/usr/bin/env python3
import os
import csv
import time
import requests
import select
from datetime import datetime
from pathlib import Path

# ======================
# パス（固定）
# ======================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CSV_DETECTED = DATA_DIR / "rfid_detect_log.csv"
CSV_USED     = DATA_DIR / "cosmetics_session_summary.csv"
CSV_USED_ALL = DATA_DIR / "cosmetics_usage_durations.csv"

# ======================
# サーバ
# ======================
SERVER = "http://localhost:8000"

# ======================
# タグ仕様（E218/E280両対応）
# ======================
TAG_PREFIXES = ("E218", "E280")
VALID_TAG_LENGTHS = {22, 23}

CHECK_INTERVAL = 5          # /tags再取得
ABSENCE_THRESHOLD = 10      # 未検出で離席扱い
SWEEP_INTERVAL = 1.0        # 入力が来なくても1秒ごとに離席判定

ENABLE_CSV = True

def normalize_tag(tag: str) -> str:
    if tag is None:
        return ""
    t = tag.strip().upper()
    t = "".join(ch for ch in t if ch.isalnum()).upper()
    return t

def is_valid_tag(tag: str) -> bool:
    if not tag:
        return False
    if not tag.startswith(TAG_PREFIXES):
        return False
    if len(tag) not in VALID_TAG_LENGTHS:
        return False
    return True

# ======================
# CSV
# ======================
def ensure_csv_headers():
    if not ENABLE_CSV:
        return

    def touch(path: Path, header):
        new = not path.exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(header)

    touch(CSV_DETECTED, ["timestamp", "tag_id", "name", "category"])
    touch(CSV_USED, ["timestamp", "name", "category"])
    touch(CSV_USED_ALL, ["timestamp", "name", "duration(sec)"])

def log_csv_detect(tag, name, category):
    if not ENABLE_CSV:
        return
    with open(CSV_DETECTED, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag, name, category])

def log_csv_used_once(name, category):
    if not ENABLE_CSV:
        return
    with open(CSV_USED, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, category])

def log_csv_duration(name, duration):
    if not ENABLE_CSV:
        return
    with open(CSV_USED_ALL, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, int(duration)])

# ======================
# HID探索
# ======================
def find_hid_device():
    print("\n🔍 RFIDリーダー接続待ち…")
    while True:
        for name in os.listdir("/dev"):
            if not name.startswith("hidraw"):
                continue
            dev = f"/dev/{name}"
            try:
                with open(dev, "rb"):
                    print(f"✅ RFID リーダー検出: {dev}")
                    return dev
            except Exception:
                continue
        time.sleep(1)

# ======================
# 8byte HIDキーボード読み取り
# ======================
KEYMAP = {
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4",
    0x22: "5", 0x23: "6", 0x24: "7", 0x25: "8",
    0x26: "9", 0x27: "0",
    0x04: "a", 0x05: "b", 0x06: "c", 0x07: "d",
    0x08: "e", 0x09: "f", 0x0A: "g", 0x0B: "h",
    0x0C: "i", 0x0D: "j", 0x0E: "k", 0x0F: "l",
    0x10: "m", 0x11: "n", 0x12: "o", 0x13: "p",
    0x14: "q", 0x15: "r", 0x16: "s", 0x17: "t",
    0x18: "u", 0x19: "v", 0x1A: "w", 0x1B: "x",
    0x1C: "y", 0x1D: "z",
}

def open_hid_nonblocking(hid_path: str):
    # ノンブロッキングで開く（入力が来なくてもSWEEPを回すため）
    fd = os.open(hid_path, os.O_RDONLY | os.O_NONBLOCK)
    return fd

def read_one_tag_from_fd(fd: int):
    """
    fdから読める分だけ読む（ノンブロッキング）。
    Enter(0x28)が来たら1タグ確定して返す。
    何も確定しなければNone。
    """
    buf = getattr(read_one_tag_from_fd, "_buf", "")
    try:
        data = os.read(fd, 8)
        # 読めない/データなし
        if not data or len(data) < 3:
            setattr(read_one_tag_from_fd, "_buf", buf)
            return None

        keycode = data[2]
        if keycode in KEYMAP:
            buf += KEYMAP[keycode].upper()
        elif keycode == 0x28:  # Enter
            tag = buf.strip().upper()
            buf = ""
            setattr(read_one_tag_from_fd, "_buf", buf)
            return tag

        setattr(read_one_tag_from_fd, "_buf", buf)
        return None

    except BlockingIOError:
        setattr(read_one_tag_from_fd, "_buf", buf)
        return None
    except OSError:
        # 切断など
        return "___HID_DISCONNECTED___"

# ======================
# サーバ通信
# ======================
def fetch_tags():
    try:
        r = requests.get(f"{SERVER}/tags", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return {normalize_tag(t["tag_id"]): {"name": t["name"], "category": t.get("category", "")} for t in data}
    except Exception as e:
        print(f"⚠ /tags取得エラー: {e}")
    return {}

def post_usage_event(tag_id, name, category, event_type, duration_sec=None):
    payload = {
        "tag_id": normalize_tag(tag_id),
        "name": name,
        "category": category,
        "event_type": event_type,
    }
    if duration_sec is not None:
        payload["duration_sec"] = int(duration_sec)
    try:
        requests.post(f"{SERVER}/usage-event", json=payload, timeout=3)
    except Exception as e:
        print(f"⚠ /usage-event 送信失敗: {e}")

def send_feedback(msg, img=None):
    try:
        requests.post(f"{SERVER}/feedback", json={"message": msg, "image": img}, timeout=3)
        print(f"💬 褒め送信: {msg}")
    except Exception as e:
        print(f"⚠ フィードバック送信失敗: {e}")

# ======================
# 離席判定（入力がなくても回せるよう関数化）
# ======================
def sweep_absence(state, tags_meta, now):
    for tid, st in state.items():
        if tid not in tags_meta:
            continue
        if st["last_seen"] is None:
            continue

        if st["is_present"] and (now - st["last_seen"] > ABSENCE_THRESHOLD):
            st["is_present"] = False
            st["absent_since"] = now
            print(f"🚫 離席: {st['name']} / {st['category']}")

            post_usage_event(tid, st["name"], st["category"], "absent_start")

            # リップ判定（表記揺れ対策）
            if st["category"].strip() == "リップ":
                post_usage_event(tid, st["name"], st["category"], "lip_trigger")
                send_feedback(
                    "今日も化粧してえらい！！",
                    f"{SERVER}/static/imgs/ikemenn.png"
                )

# ======================
# main
# ======================
def main():
    print("=== RFID Reader START ===")
    print("CWD:", os.getcwd())
    print("LOG DIR:", DATA_DIR)
    ensure_csv_headers()

    tags_meta = {}
    last_meta_fetch = 0.0
    last_sweep = 0.0

    # state[tag_id] = {name, category, is_present, last_seen, absent_since, session_logged}
    state = {}

    hid_path = find_hid_device()
    fd = open_hid_nonblocking(hid_path)
    print("✅ HID opened (non-blocking)")

    while True:
        now = time.time()

        # /tags 定期更新
        if (now - last_meta_fetch > CHECK_INTERVAL) or (not tags_meta):
            tags_meta = fetch_tags()
            last_meta_fetch = now

            # stateに反映
            for tid, meta in tags_meta.items():
                if tid not in state:
                    state[tid] = {
                        "name": meta["name"],
                        "category": meta["category"],
                        "is_present": False,
                        "last_seen": None,
                        "absent_since": None,
                        "session_logged": False,
                    }
                else:
                    state[tid]["name"] = meta["name"]
                    state[tid]["category"] = meta["category"]

        # 入力がなくても定期スイープ
        if now - last_sweep >= SWEEP_INTERVAL:
            sweep_absence(state, tags_meta, now)
            last_sweep = now

        # fdが読めるか（selectで待つ。短く待ってスイープ優先）
        rlist, _, _ = select.select([fd], [], [], 0.2)
        if not rlist:
            continue

        tag_raw = read_one_tag_from_fd(fd)
        if tag_raw is None:
            continue
        if tag_raw == "___HID_DISCONNECTED___":
            print("⚠ RFID切断 → 再接続待ち")
            try:
                os.close(fd)
            except Exception:
                pass
            hid_path = find_hid_device()
            fd = open_hid_nonblocking(hid_path)
            continue

        tag = normalize_tag(tag_raw)
        if not is_valid_tag(tag):
            # デバッグしたいならここをprintしてもOK
            continue

        # 未登録タグは無視
        if tag not in tags_meta:
            print(f"⚠ 未登録タグ: {tag}")
            continue

        name = tags_meta[tag]["name"]
        category = tags_meta[tag]["category"]

        print(f"🎯 検出: {name} / {category} ({tag})")
        log_csv_detect(tag, name, category)

        # state準備
        if tag not in state:
            state[tag] = {
                "name": name, "category": category,
                "is_present": False, "last_seen": None,
                "absent_since": None, "session_logged": False
            }
        s = state[tag]

        # absent→present（復帰）
        if not s["is_present"]:
            if s["absent_since"] is not None:
                duration = int(now - s["absent_since"])

                log_csv_duration(s["name"], duration)
                if not s["session_logged"]:
                    log_csv_used_once(s["name"], s["category"])
                    s["session_logged"] = True

                post_usage_event(tag, s["name"], s["category"], "present_return", duration_sec=duration)

            s["is_present"] = True
            s["absent_since"] = None

        s["last_seen"] = now

if __name__ == "__main__":
    main()
