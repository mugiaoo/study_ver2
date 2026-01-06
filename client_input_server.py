#!/usr/bin/env python3
import os
import csv
import time
import requests
from datetime import datetime
from pathlib import Path

# ======================
# パス（相対問題を潰す）
# ======================
BASE_DIR = Path(__file__).resolve().parent

CSV_DETECTED = str(BASE_DIR / "rfid_detect_log.csv")
CSV_USED = str(BASE_DIR / "cosmetics_session_summary.csv")
CSV_USED_ALL = str(BASE_DIR / "cosmetics_usage_durations.csv")
# DATA_DIR = BASE_DIR / "logs"
# DATA_DIR.mkdir(parents=True, exist_ok=True)

# CSV_DETECTED = DATA_DIR / "rfid_detect_log.csv"
# CSV_USED     = DATA_DIR / "cosmetics_session_summary.csv"
# CSV_USED_ALL = DATA_DIR / "cosmetics_usage_durations.csv"

# ======================
# サーバ設定
# ======================
SERVER = "http://localhost:8000"

# ======================
# タグ仕様（serverと統一）
# ======================
TAG_PREFIX = "E28"
VALID_TAG_LENGTHS = {22, 23}
TAG_LENGTHS = VALID_TAG_LENGTHS  # 互換

CHECK_INTERVAL = 5
ABSENCE_THRESHOLD = 10

# CSVを残したいなら True（DBだけで良いなら False）
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
    if not tag.startswith(TAG_PREFIX):
        return False
    if len(tag) not in VALID_TAG_LENGTHS:
        return False
    return True

# ======================
# CSV 初期化
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
    try:
        with open(CSV_DETECTED, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag, name, category])
    except Exception as e:
        print("❌ CSV書き込み失敗:", CSV_DETECTED, e)

def log_csv_used_once(name, category):
    if not ENABLE_CSV:
        return
    try:
        with open(CSV_USED, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, category])
    except Exception as e:
        print("❌ CSV書き込み失敗:", CSV_USED, e)

def log_csv_duration(name, duration):
    if not ENABLE_CSV:
        return
    try:
        with open(CSV_USED_ALL, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, int(duration)])
    except Exception as e:
        print("❌ CSV書き込み失敗:", CSV_USED_ALL, e)

# ======================
# HID探索（/dev/hidraw*）
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

def read_hid_line(hid_path):
    """
    SR3308が「ASCII + 改行」を送る想定。
    ただし機種差があるので、ここが合わない場合は read_single_tag.py方式(8byte HID report)へ切替。
    """
    try:
        with open(hid_path, "rb") as hid:
            buf = b""
            while True:
                b = hid.read(1)
                if not b:
                    return None
                if b in (b"\r", b"\n"):
                    tag = buf.decode("ascii", errors="ignore").strip().upper()
                    return tag
                buf += b
    except Exception:
        print("⚠ RFID切断 or 権限不足 → 再接続待ち")
        return None

# ======================
# サーバからタグ一覧取得
# ======================
def fetch_tags():
    try:
        r = requests.get(f"{SERVER}/tags", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return {
                normalize_tag(t["tag_id"]): {"name": t["name"], "category": t.get("category", "")}
                for t in data
            }
    except Exception as e:
        print(f"⚠ /tags取得エラー: {e}")
    return {}

# ======================
# サーバへ使用イベント送信（DB記録）
# ======================
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

# ======================
# フィードバック送信
# ======================
def send_feedback(msg, img=None):
    try:
        requests.post(f"{SERVER}/feedback", json={"message": msg, "image": img}, timeout=3)
        print(f"💬 褒め送信: {msg}")
    except Exception as e:
        print(f"⚠ フィードバック送信失敗: {e}")

# ======================
# メイン
# ======================
def main():
    print("=== RFID Reader START ===")
    print("CWD:", os.getcwd())
    print("LOG DIR:", DATA_DIR)
    ensure_csv_headers()

    tags_meta = {}
    last_meta_fetch = 0.0

    # 状態
    state = {}
    # state[tag_id] = {
    #   name, category,
    #   is_present: bool,
    #   last_seen: float|None,
    #   absent_since: float|None,
    #   session_logged: bool
    # }

    hid_path = find_hid_device()

    while True:
        tag_raw = read_hid_line(hid_path)
        now = time.time()

        if tag_raw is None:
            hid_path = find_hid_device()
            continue

        # タグ一覧更新
        if (now - last_meta_fetch > CHECK_INTERVAL) or (not tags_meta):
            tags_meta = fetch_tags()
            last_meta_fetch = now
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

        tag = normalize_tag(tag_raw)

        # フォーマット判定
        if not is_valid_tag(tag):
            continue

        # 未登録は無視（登録UIで登録する）
        if tag not in tags_meta:
            print(f"⚠ 未登録タグ: {tag}")
            continue

        name = tags_meta[tag]["name"]
        category = tags_meta[tag]["category"]

        # 検出ログ
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

        # ① present にする（absent→presentなら復帰＝使用終了）
        if not s["is_present"]:
            if s["absent_since"] is not None:
                duration = int(now - s["absent_since"])

                # CSV（任意）
                log_csv_duration(s["name"], duration)
                if not s["session_logged"]:
                    log_csv_used_once(s["name"], s["category"])
                    s["session_logged"] = True

                # DB（必須：サーバに送る）
                post_usage_event(tag, s["name"], s["category"], "present_return", duration_sec=duration)

            s["is_present"] = True
            s["absent_since"] = None

        # last_seen 更新
        s["last_seen"] = now

        # ② 離席判定スイープ（各検出のたびに全タグ見る）
        for tid, st in state.items():
            if tid not in tags_meta:
                continue
            if st["last_seen"] is None:
                continue

            if st["is_present"] and (now - st["last_seen"] > ABSENCE_THRESHOLD):
                st["is_present"] = False
                st["absent_since"] = now
                print(f"🚫 離席: {st['name']} / {st['category']}")

                # DB：離席開始
                post_usage_event(tid, st["name"], st["category"], "absent_start")

                # リップをトリガに褒める（仕様）
                if st["category"] == "リップ":
                    # DB：リップトリガも記録したいなら
                    post_usage_event(tid, st["name"], st["category"], "lip_trigger")

                    send_feedback(
                        "今日も化粧してえらい！！",
                        f"{SERVER}/static/imgs/ikemenn.png"
                    )

if __name__ == "__main__":
    main()
