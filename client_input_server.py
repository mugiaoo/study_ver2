import sys
import tty
import termios
import csv
import os
import time
import requests
from datetime import datetime

DB_NAME = "rfid.db"  # 使っていませんが念のため残し
CSV_DETECTED = "detected_tags.csv"
CSV_USED = "used_items.csv"
CHECK_INTERVAL = 5  # 5秒ごとにサーバー照合・更新判定
TAG_LENGTHS = [22, 23]
TAG_PREFIX = "E2180"

# 全角英数字・漢数字を半角英数字に変換する関数
def convert_full_and_kanji_to_halfwidth(s):
    zenkaku = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    hankaku = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    trans_table = str.maketrans(zenkaku, hankaku)
    s = s.translate(trans_table)

    kanji_to_num = {
        "〇": "0", "一": "1", "二": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"
    }
    for kanji, num in kanji_to_num.items():
        s = s.replace(kanji, num)
    return s

# ターミナルから1文字読み込み（ノンブロッキングでないシンプル版）
def get_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

# CSVにタグを記録
def save_detected_tag(tag_id, name=None):
    header_needed = not os.path.exists(CSV_DETECTED)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_DETECTED, mode='a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if header_needed:
            if name:
                writer.writerow(["timestamp", "tag_id", "name"])
            else:
                writer.writerow(["timestamp", "tag_id"])
        if name:
            writer.writerow([timestamp, tag_id, name])
        else:
            writer.writerow([timestamp, tag_id])

# CSVに使用されていないアイテム名を書き込む
def save_unused_items(names):
    if not names:
        return
    header_needed = not os.path.exists(CSV_USED)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_USED, mode='a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if header_needed:
            writer.writerow(["timestamp", "name"])
        for name in names:
            writer.writerow([timestamp, name])

# サーバーからタグ情報を取得し、使用中（20秒検出されていない）商品の名前を返す
def check_server(tags_last_seen):
    """
    tags_last_seen: dict{tag_id:str : last_seen_epoch:float}

    戻り値:
    {
        "in_use_names": [名前のリスト],
        "tag_id_to_name": {tag_id: name}
    }
    """
    try:
        # まずタグ一覧取得（tag_id→name）
        tag_response = requests.get("http://localhost:8000/tags", timeout=3)
        if tag_response.status_code != 200:
            return {"in_use_names": [], "tag_id_to_name": {}}
        tag_data = tag_response.json()
        tag_id_to_name = {t["tag_id"]: t["name"] for t in tag_data}

        # 現在時刻
        now = time.time()

        # 20秒以上検出されていないタグを抽出
        in_use_names = []
        for tag_id, name in tag_id_to_name.items():
            last_seen = tags_last_seen.get(tag_id)
            # 登録タグで、20秒以内に検出されてなければ「使用中」
            if last_seen is None or now - last_seen > 20:
                in_use_names.append(name)

        return {"in_use_names": in_use_names, "tag_id_to_name": tag_id_to_name}
    except Exception as e:
        # サーバー接続失敗時は空リスト返す
        return {"in_use_names": [], "tag_id_to_name": {}}

def main():
    print("=== RFIDタグ読み取りクライアント ===")
    print("[待機] Enterで読み取り開始 / ESCまたはCtrl+Cで終了")

    buffer = ""
    tags_last_seen = {}  # tag_id:str -> last_seen unixtime
    known_tags = {}  # サーバーから取得したtag_id->nameの辞書（毎回更新）
    unused_logged = set()  # すでにused_items.csvに記録した商品名の重複防止用

    try:
        while True:
            ch = get_key()

            # ESCキー（27）なら終了
            if ord(ch) == 27:
                print("\n[終了] ESCが押されました。終了します。")
                break
            # Ctrl+C（割り込み）でも終了できるが、ここでは無視してexceptで捕捉
            # Enterでバッファをリセットしタグ処理
            if ch == '\r' or ch == '\n':
                tag_candidate = buffer.strip()
                buffer = ""

                # 半角化＆漢数字変換
                tag_candidate = convert_full_and_kanji_to_halfwidth(tag_candidate)

                # E2180から始まり長さ22か23かどうかチェック
                if tag_candidate.startswith(TAG_PREFIX) and len(tag_candidate) in TAG_LENGTHS:
                    # タグの最終検出時刻を更新
                    tags_last_seen[tag_candidate] = time.time()

                    # サーバーから最新タグ一覧を取得（簡易で毎回取得してもよいが負荷考慮し間隔を空けるほうが良い）
                    # ここでは5秒以上経過したら取得
                    now = time.time()
                    if not known_tags or now - max(tags_last_seen.values(), default=0) > CHECK_INTERVAL:
                        server_result = check_server(tags_last_seen)
                        known_tags = server_result["tag_id_to_name"]

                    # detected_tags.csv にタイムスタンプ＋ID＋商品名を保存
                    name = known_tags.get(tag_candidate, None)
                    save_detected_tag(tag_candidate, name)

                    # ターミナルに表示（タイムスタンプ, ID, 商品名）
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if name:
                        print(f"{timestamp} | {tag_candidate} | {name}")
                    else:
                        print(f"{timestamp} | {tag_candidate} | Unknown")

                    # 未検出（20秒以上前）の商品をused_items.csvに書く（重複は避ける）
                    in_use_names = server_result.get("in_use_names", [])
                    new_unused = [n for n in in_use_names if n not in unused_logged]
                    if new_unused:
                        save_unused_items(new_unused)
                        unused_logged.update(new_unused)

                else:
                    # 無効なタグは無視して何も出さない
                    pass

            else:
                # 入力文字をバッファに追加（無駄な表示しない）
                buffer += ch

    except KeyboardInterrupt:
        print("\n[終了] Ctrl+Cが押されました。終了します。")

if __name__ == "__main__":
    main()
