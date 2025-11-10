import sys
import time
import termios
import tty
import pyperclip

HID_DEVICE_PATH = "/dev/hidraw0"

TAG_PREFIX = "E28"  # E280119..., E28011A... すべて対応
VALID_LENGTHS = [22, 23]

# HID キーマップ（client_input と統一）
KEYMAP = {
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

def wait_for_space_or_esc():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                return 'ESC'
            elif ch == ' ':
                return 'SPACE'
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def read_single_tag_hid():
    """ HID リーダーから1つのタグを読む """
    try:
        with open(HID_DEVICE_PATH, "rb") as hid:
            buffer = ""
            print("📡 タグをかざしてください...")

            while True:
                data = hid.read(8)
                keycode = data[2]

                if keycode in KEYMAP:
                    buffer += KEYMAP[keycode].upper()

                elif keycode == 0x28:  # Enter
                    tag = buffer.strip()
                    return tag

    except Exception as e:
        print(f"⚠ HID 読取エラー: {e}")
        return ""

def main():
    print("=== RFID タグ登録ツール (HID対応) ===")
    print("スペースキーで読み取り開始 / ESCで終了\n")

    while True:
        print("⏸ スペースキーで読み取る:")
        key = wait_for_space_or_esc()

        if key == 'ESC':
            print("🔚 終了します")
            break

        tag = read_single_tag_hid()

        if not tag:
            print("⚠ 読み取り失敗\n")
            continue

        if tag.startswith(TAG_PREFIX) and len(tag) in VALID_LENGTHS:
            pyperclip.copy(tag)
            print(f"✅ 読み取り成功: {tag}")
            print("📋 クリップボードにコピーしました。フォームへ貼り付けてください。\n")
        else:
            print(f"❌ 無効なタグです（取得値: {tag}）")
            print(f"⛔ 『{TAG_PREFIX}』で始まり、長さ {VALID_LENGTHS} が必要です\n")

if __name__ == "__main__":
    main()
