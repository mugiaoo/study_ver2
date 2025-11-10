import os
import csv
import time
import requests
from datetime import datetime

# ======================
# 設定
# ======================
CSV_DETECTED = "rfid_detect_log.csv"
CSV_USED = "cosmetics_session_summary.csv"        # 一度だけ記録される
CSV_USED_ALL = "cosmetics_usage_durations.csv"    # 使用時間を全保存

TAG_PREFIX = "E2180"
TAG_LENGTHS = [22, 23]
CHECK_INTERVAL = 5
INACTIVE_TIME = 10


# ======================
# CSV 初期化
# ======================
def initialize_csvs():
    for path, header in [
        (CSV_USED, ["timestamp", "name", "category"]),
        (CSV_USED_ALL, ["timestamp", "name", "duration(sec)"])
    ]:
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(header)


# ======================
# HID デバイス探索（接続されるまで待つ）
# ======================
def find_hid_device():
    """RFIDリーダーが接続されるまで待機"""
    while True:
        hid_list = [f"/dev/{d}" for d in os.listdir("/dev") if d.startswith("hidraw")]

        for dev in hid_list:
            try:
                with open(dev, "rb") as f:
                    pass
                print(f"[RFID接続検出] 使用デバイス: {dev}")
                return dev
            except PermissionError:
                continue
            except:
                continue

        print("[待機] RFIDリーダーの電源を入れてください...", end="\r")
        time.sleep(1)


# ======================
# HID からタグ読取
# ======================
def read_hid_input(hid_path):
    """ HID キーボード型 RFID リーダーからタグ文字列を読む """
    keymap = {
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

    try:
        with open(hid_path, "rb") as hid:
            buffer = ""
            while True:
                data = hid.read(8)
                keycode = data[2]

                if keycode in keymap:
                    buffer += keymap[keycode].upper()

                elif keycode == 0x28:  # Enter
                    tag = buffer.strip()
                    buffer = ""
                    return tag

    except Exception:
        print("\n[RFID切断] 接続が外れました。再接続待ち…")
        return None


# ======================
# タグ一覧取得
# ======================
def fetch_tags():
    try:
        res = requests.get("http://localhost:8000/tags", timeout=3)
        if res.status_code == 200:
            return {t["tag_id"]: {"name": t["name"], "category": t.get("category", "")}
                    for t in res.json()}
    except:
        pass
    return {}


# ======================
# 検出ログ保存
# ======================
def save_detect(tag, name, category):
    new = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "tag_id", "name", "category"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag, name, category])


# ======================
# フィードバック送信
# ======================
def send_feedback(msg, img=None):
    try:
        requests.post("http://localhost:8000/feedback",
                      json={"message": msg, "image": img}, timeout=3)
        print(f"[褒め言葉送信] {msg}")
    except:
        print("[送信失敗] フィードバック送信エラー")


# ======================
# メイン処理
# ======================
def main():
    print("=== RFID Reader (HID hotplug) START ===")
    initialize_csvs()

    tags_seen = {}
    logged_used = set()
    last_fetch = 0

    while True:
        # ──────────────────────────────
        # ✅ RFID が接続されるまで待つ
        # ──────────────────────────────
        hid_path = find_hid_device()

        # ──────────────────────────────
        # ✅ 接続後は読取ループに入る
        # ──────────────────────────────
        while True:
            now = time.time()

            # タグ読取
            tag = read_hid_input(hid_path)

            # リーダーが抜かれた → 探索に戻る
            if tag is None:
                break

            # タグ情報更新
            if now - last_fetch > CHECK_INTERVAL:
                tag_data = fetch_tags()
                last_fetch = now

            # フォーマットチェック
            if tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
                info = tag_data.get(tag)
                if info:
                    name = info["name"]
                    category = info["category"]
                    save_detect(tag, name, category)

                    tags_seen[tag] = {"first": now, "last": now}
                    print(f"[検出] {name} / {category}")

            # 使用終了チェック
            for tid, d in list(tags_seen.items()):
                if now - d["last"] > INACTIVE_TIME:
                    info = tag_data.get(tid)
                    name = info["name"]
                    category = info["category"]
                    duration = int(d["last"] - d["first"])

                    # 全使用記録
                    with open(CSV_USED_ALL, "a", encoding="utf-8", newline="") as f:
                        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                name, duration])

                    # セッション記録（重複なし）
                    if name not in logged_used:
                        with open(CSV_USED, "a", encoding="utf-8", newline="") as f:
                            csv.writer(f).writerow(
                                [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, category]
                            )
                        logged_used.add(name)

                        # リップなら褒め言葉
                        if category == "リップ":
                            send_feedback("今日も化粧してえらい！！",
                                          "http://localhost:8000/static/imgs/ikemen.png")

                    del tags_seen[tid]


if __name__ == "__main__":
    main()
