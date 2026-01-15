#!/usr/bin/env python3
import pyperclip

def normalize_tag(tag: str) -> str:
    if not tag:
        return ""
    t = tag.strip().upper()
    t = "".join(ch for ch in t if ch.isalnum()).upper()
    return t

def main():
    print("=== RFID タグ登録ツール (Mac版・キーボード入力) ===")
    print("手順：")
    print(" 1. このターミナルをアクティブにする（クリック）")
    print(" 2. RFIDリーダーにタグをかざす")
    print(" 3. リーダーが自動でIDを打ち込み、Enter まで送ってくれる")
    print(" 4. 読み取るたびにクリップボードへコピーされます")
    print("終了したいときは、空の行でEnter、または Ctrl+C\n")

    while True:
        try:
            line = input("タグをかざしてください（終了: 何も入力せずEnter）: ")
        except EOFError:
            break

        line = line.strip()
        if not line:
            print("🔚 終了します")
            break

        tag = normalize_tag(line)
        suffix = tag[-5:] if len(tag) >= 5 else tag

        try:
            pyperclip.copy(tag)
            copied = True
        except Exception as e:
            print(f"⚠ クリップボードコピーに失敗しました: {e}")
            copied = False

        print(f"✅ 読み取り成功: {tag}")
        print(f"   末尾5桁: {suffix}")
        if copied:
            print("📋 フルIDをクリップボードにコピーしました。register-ui のタグID欄に貼り付けてください。\n")
        else:
            print("⚠ クリップボードへコピーできなかったので、上のIDを手動でコピーしてください。\n")

if __name__ == "__main__":
    main()
