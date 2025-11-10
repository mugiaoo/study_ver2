import sys
import csv
import os
import time
import requests
from datetime import datetime

# === 定数設定 ===
CSV_DETECTED = "rfid_detect_log.csv"
CSV_USED = "cosmetics_session_summary.csv"
CSV_USED_ALL = "cosmetics_usage_durations.csv"

TAG_LENGTHS = [22, 23]
TAG_PREFIX = "E2180"
CHECK_INTERVAL = 5
INACTIVE_TIME = 10

RFID_DEVICE = "/dev/hidraw0"  # USBキーボード型RFIDリーダー入力デバイス

# === キーマップ定義（数字＋英字のみ対応） ===
KEYMAP = {
    30: '1', 31: '2', 32: '3', 33: '4', 34: '5',
    35: '6', 36: '7', 37: '8', 38: '9', 39: '0',
    4: 'a', 5: 'b', 6: 'c', 7: 'd', 8: 'e', 9: 'f'
}

# === CSV初期化 ===
def initialize_used_csvs():
    for csv_path, headers in [
        (CSV_USED, ["timestamp", "name", "category"]),
        (CSV_USED_ALL, ["timestamp", "name", "duration(sec)"])
    ]:
        with open(csv_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)

# === サーバーからタグ一覧取得 ===
def fetch_tags():
    try:
        res = requests.get("http://localhost:8000/tags", timeout=3)
        if res.status_code == 200:
            return {t["tag_id"]: {"name": t["name"], "category": t.get("category", "")} for t in res.json()}
    except Exception as e:
        print(f"[タグ取得エラー] {e}")
    return {}

# === 検出ログ保存 ===
def save_to_detected_csv(tag_id, name, category=""):
    new_file = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "tag_id", "name", "category"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag_id, name, category])

# === フィードバック送信 ===
def send_feedback(message="今日も化粧してえらい！！", image_url=None):
    try:
        url = "http://localhost:8000/feedback"
        payload = {"message": message}
        if image_url:
            payload["image"] = image_url
        response = requests.post(url, json=payload, timeout=3)
        if response.status_code == 200:
            print("[送信成功]", message)
        else:
            print(f"[送信失敗] ステータスコード: {response.status_code}")
    except Exception as e:
        print(f"[送信エラー] {e}")

# === RFIDリーダーからタグ読み取り ===
def read_rfid_tag(device_path=RFID_DEVICE):
    """USBキーボード型リーダーからタグIDを1回分読み取る"""
    tag = ""
    try:
        with open(device_path, 'rb') as dev:
            while True:
                data = dev.read(8)
                key_code = data[2]
                if key_code == 0:
                    continue
                if key_code == 40:  # Enterキー
                    return tag.strip()
                char = KEYMAP.get(key_code)
                if char:
                    tag += char
    except Exception as e:
        print(f"[RFID読取エラー] {e}")
        time.sleep(1)
        return None

# === メイン ===
def main():
    initialize_used_csvs()
    known_tags = fetch_tags()
    print("=== RFIDタグ監視開始 ===")

    tags_seen = {}  # {tag_id: {"first": 時刻, "last": 時刻}}
    logged_used = set()
    last_check_time = time.time()

    while True:
        tag = read_rfid_tag()
        now = time.time()

        if tag and tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
            info = known_tags.get(tag)
            if info:
                name = info["name"]
                category = info.get("category", "")
                print(f"[検出] {name} ({category})")
                save_to_detected_csv(tag, name, category)
                tags_seen[tag] = {"first": now, "last": now}

        # 使用終了チェック
        if time.time() - last_check_time > INACTIVE_TIME:
            inactive = []
            for tag_id, data in list(tags_seen.items()):
                if now - data["last"] > INACTIVE_TIME:
                    info = known_tags.get(tag_id, {})
                    name = info.get("name", "Unknown")
                    category = info.get("category", "")
                    duration = int(data["last"] - data["first"])

                    # 使用履歴保存
                    with open(CSV_USED_ALL, 'a', encoding='utf-8', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, duration])

                    if name not in logged_used:
                        with open(CSV_USED, 'a', encoding='utf-8', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, category])
                        logged_used.add(name)

                        # リップ判定
                        if category == "リップ":
                            message = "今日も化粧してえらい！！"
                            image_url = "http://localhost:8000/static/imgs/ikemen.png"
                            print("[褒め言葉表示]", message)
                            send_feedback(message, image_url)

                    del tags_seen[tag_id]
            last_check_time = now

        time.sleep(0.1)

if __name__ == "__main__":
    main()
