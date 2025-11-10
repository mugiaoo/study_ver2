=import sys
import tty
import termios
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
CHECK_INTERVAL = 5      # サーバー問い合わせ間隔
INACTIVE_TIME = 10      # 使用終了と判断する非検出時間（秒）

# === CSV初期化 ===
def initialize_used_csvs():
    for csv_path, headers in [
        (CSV_USED, ["timestamp", "name", "category"]),
        (CSV_USED_ALL, ["timestamp", "name", "duration(sec)"])
    ]:
        with open(csv_path, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)

# === systemdで動作中か判定 ===
def is_running_under_systemd():
    return not sys.stdin.isatty()

# === 非表示でキー入力取得 ===
def get_hidden_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# === 全角→半角変換 ===
def convert_full_and_kanji_to_halfwidth(s):
    zenkaku = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    hankaku = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    s = s.translate(str.maketrans(zenkaku, hankaku))
    kanji_to_num = {"〇": "0", "一": "1", "二": "2", "三": "3", "四": "4",
                    "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
    for k, v in kanji_to_num.items():
        s = s.replace(k, v)
    return s

# === サーバーからタグ一覧取得 ===
def fetch_tags():
    try:
        res = requests.get("http://localhost:8000/tags", timeout=3)
        if res.status_code == 200:
            return {t["tag_id"]: {"name": t["name"], "category": t.get("category", "")} for t in res.json()}
    except Exception as e:
        print(f"[タグ取得エラー] {e}")
    return {}

# === 検出CSVへ保存 ===
def save_to_detected_csv(tag_id, name, category=""):
    if not name:
        return
    new_file = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "tag_id", "name", "category"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag_id, name, category])

# === 起動時にタグ一覧CSV初期化 ===
def initialize_detected_tags_csv():
    try:
        response = requests.get("http://localhost:8000/tags", timeout=3)
        if response.status_code != 200:
            print("[警告] サーバーからタグ一覧を取得できませんでした。")
            return {}
        tag_data = response.json()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(CSV_DETECTED, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "tag_id", "name", "category"])
            for tag in tag_data:
                writer.writerow([now_str, tag["tag_id"], tag["name"], tag["category"]])
        return {tag["tag_id"]: {"name": tag["name"], "category": tag["category"]} for tag in tag_data}
    except Exception as e:
        print(f"[エラー] 初期化中にエラーが発生: {e}")
        return {}

# === フィードバック送信 ===
def send_feedback(message="今日も化粧してえらい！！", image_url=None):
    try:
        url = "http://localhost:8000/feedback"
        payload = {"message": message}
        if image_url:
            payload["image"] = image_url
        response = requests.post(url, json=payload, timeout=3)
        if response.status_code == 200:
            print("[送信成功] フィードバック送信:", message, image_url)
        else:
            print(f"[送信失敗] ステータスコード: {response.status_code}")
    except Exception as e:
        print(f"[送信エラー] {e}")

# === メイン ===
def main():
    initialize_used_csvs()
    known_tags = initialize_detected_tags_csv()
    print("=== RFIDタグ読み取りクライアント ===")
    print("[待機] タグを読み取ると記録 / ESCまたはCtrl+Cで終了")

    buffer = ""
    tag_id_to_info = {}
    last_fetch = 0
    logged_used = set()
    tags_seen = {}  # { tag_id: {"first": 時刻, "last": 時刻} }

    last_check_time = time.time()
    auto_mode = is_running_under_systemd()

    try:
        while True:
            if auto_mode:
                time.sleep(1)
                tag = ""
            else:
                ch = get_hidden_key()
                if ord(ch) == 27:
                    print("\n[終了] 終了します。")
                    break
                if ch == '\r' or ch == '\n':
                    tag = convert_full_and_kanji_to_halfwidth(buffer.strip())
                    buffer = ""
                else:
                    buffer += ch
                    continue

            now = time.time()

            # 定期的にタグ情報を更新
            if now - last_fetch > CHECK_INTERVAL or not tag_id_to_info:
                tag_id_to_info = fetch_tags()
                last_fetch = now

            # タグが入力された場合のみ処理
            if tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
                info = tag_id_to_info.get(tag)
                if info:
                    name = info["name"]
                    category = info.get("category", "")
                    save_to_detected_csv(tag, name, category)
                    if tag not in tags_seen:
                        tags_seen[tag] = {"first": now, "last": now}
                    else:
                        tags_seen[tag]["last"] = now

            # 使用終了チェック
            current_time = time.time()
            if current_time - last_check_time > INACTIVE_TIME:
                inactive_tags = []
                for tag_id, info in tag_id_to_info.items():
                    seen_data = tags_seen.get(tag_id)
                    if not seen_data:
                        continue

                    last_seen = seen_data["last"]
                    first_seen = seen_data["first"]
                    if current_time - last_seen > INACTIVE_TIME:
                        name = info["name"]
                        category = info.get("category", "")
                        duration = int(last_seen - first_seen)

                        # used_items_all.csv に全記録
                        with open(CSV_USED_ALL, 'a', encoding='utf-8', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, duration])

                        # used_items.csv に重複なしで記録
                        if name not in logged_used:
                            with open(CSV_USED, 'a', encoding='utf-8', newline='') as f:
                                writer = csv.writer(f)
                                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, category])
                            logged_used.add(name)

                            # 💄 リップ使用時に褒め言葉
                            if category == "リップ":
                                message = "今日も化粧してえらい！！"
                                image_url = "http://localhost:8000/static/imgs/ikemen.png"
                                send_feedback(message, image_url)

                        # タグ削除
                        del tags_seen[tag_id]

                last_check_time = current_time

    except KeyboardInterrupt:
        print("\n[終了] Ctrl+Cが押されました。終了します。")

if __name__ == "__main__":
    main()
