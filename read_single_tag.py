import sys
import tty
import termios
import pyperclip

TAG_PREFIX = "E2180"
VALID_LENGTHS = [22, 23]

# 全角英数字・漢数字を半角英数字に変換
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

# タグを1つ読み取る（Enterで確定、ESCでキャンセル）
def read_single_tag():
    buffer = ""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == '\x1b':  # ESC
                return None
            if ch == '\r' or ch == '\n':
                break
            buffer += ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    tag = convert_full_and_kanji_to_halfwidth(buffer.strip())

    if tag.startswith(TAG_PREFIX) and len(tag) in VALID_LENGTHS:
        return tag
    else:
        return "INVALID"

# スペースキーかESCを待つ
def wait_for_space_or_esc():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == '\x1b':  # ESC
                return ch
            elif ch == ' ':  # スペースキー
                return ch
            else:
                continue
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def main():
    print("=== RFIDタグ読み取りツール ===")
    print("スペースキーで読み取り開始 / ESCで終了\n")

    while True:
        print("⏸ スペースキーで読み取る:")
        key = wait_for_space_or_esc()
        if key == '\x1b':
            print("🔚 終了します。")
            break
        elif key == ' ':
            tag = read_single_tag()
            if tag is None:
                print("❌ 読み取りキャンセル\n")
            elif tag == "INVALID":
                print(f"❌ 無効なタグです（入力値: 『{tag}』）")
                print(f"⛔ 『{TAG_PREFIX}』で始まり、{VALID_LENGTHS}文字である必要があります。\n")
            else:
                pyperclip.copy(tag)
                print(f"✅ 読み取り成功: {tag}")
                print("📋 クリップボードにコピーしました。Ctrl+Vでフォームに貼り付けてください。\n")

if __name__ == "__main__":
    main()
