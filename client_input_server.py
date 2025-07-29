import sys
import tty
import termios
import csv
import os
import time
import requests
from datetime import datetime

# 定数定義
CSV_DETECTED = "detected_tags.csv"
CSV_USED = "used_items.csv"
CSV_USED_ALL = "used_items_all.csv"
TAG_LENGTHS = [22, 23]
TAG_PREFIX = "E2180"
CHECK_INTERVAL = 5
INACTIVE_TIME = 20

# 初期化：used_items.csv / used_items_all.csv を空にする
def initialize_used_csvs():
    with open(CSV_USED, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "name"])
    with open(CSV_USED_ALL, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "name"])

# 非表示でキー入力を取得（1文字）
def get_hidden_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def convert_full_and_kanji_to_halfwidth(s):
    zenkaku = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    hankaku = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    s = s.translate(str.maketrans(zenkaku, hankaku))
    kanji_to_num = {
        "〇": "0", "一": "1", "二": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"
    }
    for k, v in kanji_to_num.items():
        s = s.replace(k, v)
    return s

def fetch_tags():
    try:
        res = requests.get("http://localhost:8000/tags", timeout=3)
        if res.status_code == 200:
            return {
                t["tag_id"]: {"name": t["name"], "category": t.get("category", "")}
                for t in res.json()
            }
    except:
        pass
    return {}

def save_to_detected_csv(tag_id, name, category="") :
    if not name:
        return
    new_file = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "tag_id", "name", "category"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag_id, name, category])

def save_to_used_csv(names, logged_names):
    if not names:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_USED, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for name in names:
            if name not in logged_names:
                writer.writerow([timestamp, name])
                logged_names.add(name)

def save_to_used_all_csv(names):
    if not names:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_USED_ALL, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for name in names:
            writer.writerow([timestamp, name])

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

def send_feedback(message="💄 今日も化粧してえらい！！"):
    try:
        url = "http://localhost:8000/feedback"
        response = requests.post(url, json={"message": message}, timeout=3)
        if response.status_code == 200:
            print("[送信成功] フィードバック送信:", message)
        else:
            print(f"[送信失敗] ステータスコード: {response.status_code}")
    except Exception as e:
        print(f"[送信エラー] フィードバック送信中に例外発生: {e}")

def main():
    initialize_used_csvs()
    known_tags = initialize_detected_tags_csv()
    print("=== RFIDタグ読み取りクライアント ===")
    print("[待機] タグを読み取ると記録 / ESCまたはCtrl+Cで終了")

    buffer = ""
    tag_id_to_info = {}
    last_fetch = 0
    logged_used = set()

    current_time = time.time()
    tags_last_seen = {tag_id: current_time for tag_id in known_tags.keys()}

    # 🔽 追加：リップ読み取り記録用セット
    recently_seen_lip_tags = set()
    last_check_time = current_time

    try:
        while True:
            ch = get_hidden_key()
            if ord(ch) == 27:
                print("\n[終了] 終了します。")
                break

            if ch == '\r' or ch == '\n':
                tag = convert_full_and_kanji_to_halfwidth(buffer.strip())
                buffer = ""

                if tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
                    now = time.time()

                    if now - last_fetch > CHECK_INTERVAL or not tag_id_to_info:
                        tag_id_to_info = fetch_tags()
                        last_fetch = now

                    info = tag_id_to_info.get(tag)
                    if info:
                        name = info["name"]
                        category = info.get("category", "")
                        save_to_detected_csv(tag, name)
                        tags_last_seen[tag] = now

                        # 🔽 追加：リップカテゴリの読み取り記録
                        if category == "リップ":
                            recently_seen_lip_tags.add(tag)

                current_time = time.time()

                # 🔽 チェック間隔が経過していたら未使用処理とリップ未検出処理を行う
                if current_time - last_check_time > INACTIVE_TIME:
                    inactive_names = []
                    for t_id, data in tag_id_to_info.items():
                        last_seen = tags_last_seen.get(t_id)
                        if last_seen is None or current_time - last_seen > INACTIVE_TIME:
                            inactive_names.append(data["name"])

                    save_to_used_csv(inactive_names, logged_used)
                    save_to_used_all_csv(inactive_names)

                    # リップ使用検出（未使用から）
                    for name in inactive_names:
                        for t_id, info in known_tags.items():
                            if info["name"] == name and info.get("category") == "リップ":
                                message = "💄 今日も化粧してえらい！！"
                                print(message)
                                send_feedback(message)
                                break

                    # 🔁 記録をリセット
                    recently_seen_lip_tags.clear()
                    last_check_time = current_time

            else:
                buffer += ch

    except KeyboardInterrupt:
        print("\n[終了] Ctrl+Cが押されました。終了します。")

if __name__ == "__main__":
    main()
