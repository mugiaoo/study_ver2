import sys
import tty
import termios
import sqlite3
import csv
from datetime import datetime

DB_NAME = "rfid.db"
CSV_REGISTERED = "detected_tags.csv"
CSV_UNREGISTERED = "missing_tags.csv"

'''
キーボードから英数字を１文字ずつ受け取る
Enterを押すと、その文字列をサーバーに送信
ESCキーを押すと終了
'''

def get_key():
    #1文字だけ標準入力から受け取る
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1) # 1文字目を読み込む
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def is_registered(tag_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT 1 FROM tags WHERE tag_id=?", (tag_id,))
    result = c.fetchone()
    return result is not None

def save_to_csv(filename, tag_id):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_needed = False
    if not os.path.exists(filename):
        header_needed = True
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if header_needed:
            writer.writerow(["timestamp", "tag_id"])
        writer.writerow([timestamp, tag_id])

def get_all_registered_tags():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT tag_id FROM tags")
    tags = [row[0] for row in c.fetchall()]
    conn.close()
    return set(tags)

def save_used_tags(missing_tags):
    filename = "used_tag.csv"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_needed = not os.path.exists(filename)
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if header_needed:
            writer.writerow(["timestamp", "missing_tag_id"])
        for tag_id in missing_tags:
            writer.writerow([timestamp, tag_id])

def main():
    print("=== RFIDタグ読み取りクライアント ===")
    print("Enterキーでタグ読み取り開始、ESCキーで終了します。")

    while True:
        print("\nキーを押してください（Enter=開始、ESC=終了）:")
        key = get_key()

        if key == '\r' or key =='\n': #Enter
            input_str = input("読み取れたタグIDをスペース区切りで入力：").strip()
            detected_tags = set(input_str.split())
            if not detected_tags:
                print("タグIDが空です。再度入力してください。")
                continue

            all_tags = get_all_registered_tags()
            used_tags = all_tags - detected_tags
        
            for tag_id in detected_tags:
                if is_registered(tag_id):
                    print(f"登録済みタグ検出:{tag_id}")
                    save_to_csv(CSV_REGISTERED, tag_id)
                else:
                    print(f"未登録タグ検出:{tag_id}")
                    save_to_csv(CSV_UNREGISTERED, tag_id)
            
            print(f"\n🔹使用中（読み取れなかった）タグ数: {len(used_tags)}")
            for tag in used_tags:
                print(f"使用中のタグ:{tag}")
                save_used_tags(used_tags)   

        elif ord(key) == 27:
            print("終了します")
            break
        else:
            print(f"未対応のキーが押されました: {repr(key)}")

if __name__ == "__main__":
    import os 
    main()

