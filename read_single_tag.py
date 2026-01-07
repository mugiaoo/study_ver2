#!/usr/bin/env python3
import sys
import time
import termios
import tty
import os
import pyperclip

TAG_PREFIXES = ("E218", "E280")
VALID_LENGTHS = {22, 23}

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

def normalize_tag(tag: str) -> str:
    if not tag:
        return ""
    t = tag.strip().upper()
    t = "".join(ch for ch in t if ch.isalnum()).upper()
    return t

def is_valid_tag(tag: str) -> bool:
    if not tag.startswith(TAG_PREFIXES):
        return False
    if len(tag) not in VALID_LENGTHS:
        return False
    return True

def wait_for_space_or_esc():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                return 'ESC'
            if ch == ' ':
                return 'SPACE'
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def find_hid_device():
    print("🔍 /dev/hidraw* を探索中…")
    while True:
        for name in os.listdir("/dev"):
            if not name.startswith("hidraw"):
                continue
            dev = f"/dev/{name}"
            try:
                with open(dev, "rb"):
                    print(f"✅ 候補デバイス: {dev}")
                    return dev
            except Exception:
                continue
        time.sleep(1)

def read_single_tag_hid(hid_path):
    try:
        with open(hid_path, "rb") as hid:
            buffer = ""
            print("📡 タグをかざしてください...")
            while True:
                data = hid.read(8)
                if not data or len(data) < 3:
                    return ""
                keycode = data[2]
                if keycode in KEYMAP:
                    buffer += KEYMAP[keycode].upper()
                elif keycode == 0x28:
                    return normalize_tag(buffer)
    except Exception as e:
        print(f"⚠ HID 読取エラー: {e}")
        return ""

def main():
    print("=== RFID タグ登録ツール ===")
    print("スペースキーで読み取り開始 / ESCで終了\n")
    hid_path = find_hid_device()

    while True:
        print("⏸ スペースキーで読み取る:")
        key = wait_for_space_or_esc()
        if key == 'ESC':
            print("🔚 終了します")
            break

        tag = read_single_tag_hid(hid_path)
        if not tag:
            print("⚠ 読み取り失敗\n")
            continue

        if is_valid_tag(tag):
            pyperclip.copy(tag)
            print(f"✅ 読み取り成功: {tag}")
            print("📋 クリップボードにコピーしました（register-uiへ貼り付けてください）\n")
        else:
            print(f"❌ 無効なタグです（取得値: {tag}）")
            print(f"⛔ prefix={TAG_PREFIXES}, 長さ={sorted(VALID_LENGTHS)} が必要\n")

if __name__ == "__main__":
    main()
