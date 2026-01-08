#!/usr/bin/env python3
import sys
import time
import requests
import re

# ========= 設定 =========
PI_SERVER = "http://10.124.59.134:8000"  # ←PiのIPに変えてもOK（例 http://192.168.0.10:8000）
TAG_PREFIXES = ("E218", "E280")
VALID_TAG_LENGTHS = {22, 23}
TAG_ALLOWED_RE = re.compile(r"^[0-9A-F]+$")

def normalize_tag(s: str) -> str:
    if s is None:
        return ""
    t = s.strip().upper()
    t = "".join(ch for ch in t if ch.isalnum()).upper()
    return t

def is_valid_tag(tag: str) -> bool:
    if not tag:
        return False
    if not tag.startswith(TAG_PREFIXES):
        return False
    if len(tag) not in VALID_TAG_LENGTHS:
        return False
    if not TAG_ALLOWED_RE.match(tag):
        return False
    return True

def post_scan(tag_id: str):
    try:
        r = requests.post(f"{PI_SERVER}/scan", json={"tag_id": tag_id}, timeout=3)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)

def main():
    print("=== Mac RFID Client ===")
    print("RFIDをかざすとIDが入力されるはずです。Enterで1行確定 → Piへ送信します。")
    print("Pi:", PI_SERVER)
    print("終了: Ctrl+C\n")

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue

        tag = normalize_tag(raw)

        # SR3308が余計な文字を混ぜることがあるので、ここで弾く
        if not is_valid_tag(tag):
            # デバッグしたいなら次を有効に
            # print("[SKIP]", raw)
            continue

        code, body = post_scan(tag)
        if code is None:
            print(f"⚠ 送信失敗: {body}")
        else:
            print(f"✅ sent {tag} -> {code}")

if __name__ == "__main__":
    main()
