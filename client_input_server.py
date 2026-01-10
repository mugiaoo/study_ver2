#!/usr/bin/env python3
import sys
import requests
import re

PI_SERVER = "http://10.124.59.134:8000"  # PiのIP
TAG_PREFIXES = ("E218", "E280")
VALID_TAG_LENGTHS = {22, 23}
TAG_ALLOWED_RE = re.compile(r"^[0-9A-F]+$")

def normalize_tag(s: str) -> str:
    t = (s or "").strip().upper()
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

def main():
    print("=== Mac RFID Client ===")
    print("Enterで1行確定 → Piへ /scan POST")
    print("Pi:", PI_SERVER)
    print("終了: Ctrl+C\n")

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        tag = normalize_tag(raw)
        if not is_valid_tag(tag):
            continue

        try:
            r = requests.post(f"{PI_SERVER}/scan", json={"tag_id": tag}, timeout=3)
            print(f"✅ sent {tag} -> {r.status_code}")
        except Exception as e:
            print("⚠ 送信失敗:", e)

if __name__ == "__main__":
    main()
