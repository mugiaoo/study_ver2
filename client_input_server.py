import sys
import tty
import termios
import csv
import os
import time
import requests
from datetime import datetime

# ファイル名定数
CSV_DETECTED = "detected_tags.csv"
CSV_USED = "used_items.csv"

# タグ条件
TAG_LENGTHS = [22, 23]
TAG_PREFIX = "E2180"
CHECK_INTERVAL = 5  # サーバーとの照合間隔（秒）
INACTIVE_TIME = 20  # 読み取られないと「使用された」と見なす時間（秒）

# 入力を非表示で取得
def get_hidden_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# 全角英数・漢数字を半角に変換
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

# タグ情報をサーバーから取得
def fetch_tags():
    try:
        res = requests.get("http://localhost:8000/tags", timeout=3)
        if res.status_code == 200:
            return {t["tag_id"]: t["name"] for t in res.json()}
    except:
        pass
    return {}

# 読み取られたタグをCSVに保存（登録済みタグのみ）
def save_to_detected_csv(tag_id, name):
    if not name:
        return
    new_file = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "tag_id", "name"])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([timestamp, tag_id, name])

# 使用済み（一定時間検出されていない）アイテムをCSVに保存
def save_to_used_csv(names, logged_names):
    if not names:
        return
    new_file = not os.path.exists(CSV_USED)
    with open(CSV_USED, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "name"])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for name in names:
            if name not in logged_names:
                writer.writerow([timestamp, name])
                logged_names.add(name)

def main():
    print("=== RFIDタグ読み取りクライアント ===")
    print("[待機] タグを読み取ると記録 / ESCまたはCtrl+Cで終了")

    buffer = ""
    tag_id_to_name = {}
    last_fetch = 0
    tags_last_seen = {}  # tag_id: last_seen_timestamp
    logged_used = set()  # used_items.csv に記録済みの名前

    try:
        while True:
            ch = get_hidden_key()
            if ord(ch) == 27:  # ESCキー
                print("\n[終了] 終了します。")
                break
            if ch == '\r' or ch == '\n':
                tag = convert_full_and_kanji_to_halfwidth(buffer.strip())
                buffer = ""

                # タグ形式チェック
                if tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
                    now = time.time()

                    # サーバーからタグ一覧取得（一定間隔で更新）
                    if now - last_fetch > CHECK_INTERVAL or not tag_id_to_name:
                        tag_id_to_name = fetch_tags()
                        last_fetch = now

                    name = tag_id_to_name.get(tag)
                    if name:
                        save_to_detected_csv(tag, name)
                        tags_last_seen[tag] = now  # 最終検出時間更新

                        if name == "リップ":
                            print("💄 今日も化粧してえらい！！")

                    # 一定時間検出されていないタグの名前をused_items.csvに記録
                    current_time = time.time()
                    inactive_names = []
                    for t_id, t_name in tag_id_to_name.items():
                        last_seen = tags_last_seen.get(t_id)
                        if last_seen is None or current_time - last_seen > INACTIVE_TIME:
                            if t_name not in logged_used:
                                inactive_names.append(t_name)

                    save_to_used_csv(inactive_names, logged_used)

            else:
                buffer += ch  # 入力は画面に表示しない

    except KeyboardInterrupt:
        print("\n[終了] Ctrl+Cが押されました。終了します。")

if __name__ == "__main__":
    main()
