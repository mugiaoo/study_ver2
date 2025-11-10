import os
import csv
import time
import requests
from datetime import datetime

# ======================
# 設定（あなたの環境に合わせた最適値）
# ======================
CSV_DETECTED = "rfid_detect_log.csv"
CSV_USED = "cosmetics_session_summary.csv"
CSV_USED_ALL = "cosmetics_usage_durations.csv"

TAG_PREFIX = "E280"          # ← ここ重要
TAG_LENGTHS = [23]           # ← 必ず 23 文字だけ

CHECK_INTERVAL = 5
INACTIVE_TIME = 10


# ======================
# CSV 初期化
# ======================
def initialize_csvs():
    for path, header in [
        (CSV_USED, ["timestamp", "name", "category"]),
        (CSV_USED_ALL, ["timestamp", "name", "duration(sec)"])
    ]:
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(header)


# ======================
# HID デバイス探索
# ======================
def find_hid_device():
    print("\n🔍 RFIDリーダー接続待ち… (電源を入れてください)")

    while True:
        hid_list = [f"/dev/{d}" for d in os.listdir("/dev") if d.startswith("hidraw")]

        for dev in hid_list:
            try:
                with open(dev, "rb"):
                    print(f"\n✅ RFID リーダー検出: {dev}")
                    return dev
            except PermissionError:
                continue
            except:
                continue

        time.sleep(1)


# ======================
# HID 読み取り
# ======================
def read_hid_input(hid_path):
    """ HID キーボード型 RFID リーダーから 1 タグ読取 """
    keymap = {
        0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4",
        0x22: "5", 0x23: "6", 0x24: "7", 0x25: "8",
        0x26: "9", 0x27: "0",
        0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D",
        0x08: "E", 0x09: "F", 0x0A: "G", 0x0B: "H",
        0x0C: "I", 0x0D: "J", 0x0E: "K", 0x0F: "L",
        0x10: "M", 0x11: "N", 0x12: "O", 0x13: "P",
        0x14: "Q", 0x15: "R", 0x16: "S", 0x17: "T",
        0x18: "U", 0x19: "V", 0x1A: "W", 0x1B: "X",
        0x1C: "Y", 0x1D: "Z"
    }

    try:
        with open(hid_path, "rb") as hid:
            buffer = ""
            while True:
                data = hid.read(8)
                keycode = data[2]

                # 文字
                if keycode in keymap:
                    buffer += keymap[keycode]

                # Enterで 1 タグ確定
                elif keycode == 0x28:
                    tag = buffer.strip().upper()
                    buffer = ""
                    return tag

    except Exception:
        print("\n⚠ RFID切断 detected → 再接続待ち…")
        return None


# ======================
# /tags 取得
# ======================
def fetch_tags():
    try:
        res = requests.get("http://localhost:8000/tags", timeout=3)
        if res.status_code == 200:
            return {t["tag_id"]: {"name": t["name"], "category": t["category"]}
                    for t in res.json()}
    except:
        pass
    return {}


# ======================
# 検出ログ保存
# ======================
def save_detect(tag, name, category):
    new = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "tag_id", "name", "category"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag, name, category])


# ======================
# フィードバック送信
# ======================
def send_feedback(msg, img=None):
    try:
        requests.post(
            "http://localhost:8000/feedback",
            json={"message": msg, "image": img},
            timeout=3
        )
        print(f"💬 褒め言葉送信: {msg}")
    except:
        print("⚠ フィードバック送信に失敗")


# ======================
# メイン
# ======================
def main():
    print("=== RFID Reader START ===")
    initialize_csvs()

    tags_seen = {}
    logged_used = set()
    last_fetch = 0

    while True:
        hid_path = find_hid_device()

        while True:
            now = time.time()
            tag = read_hid_input(hid_path)

            if tag is None:
                break

            # タグ更新
            if now - last_fetch > CHECK_INTERVAL:
                tag_data = fetch_tags()
                last_fetch = now

            # フォーマットチェック
            if tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
                info = tag_data.get(tag)

                if info:
                    name = info["name"]
                    category = info["category"]

                    print(f"🎯 読取: {name} / {category}")
                    save_detect(tag, name, category)

                    tags_seen[tag] = {"first": now, "last": now}

                else:
                    print(f"⚠ 未登録タグ: {tag}")

            # 使用終了判定
            for tid, d in list(tags_seen.items()):
                if now - d["last"] > INACTIVE_TIME:
                    info = tag_data.get(tid)
                    if not info:
                        del tags_seen[tid]
                        continue

                    name = info["name"]
                    category = info["category"]
                    duration = int(d["last"] - d["first"])

                    # 全ログ
                    with open(CSV_USED_ALL, "a", encoding="utf-8", newline="") as f:
                        csv.writer(f).writerow([
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            name, duration
                        ])

                    # 一回だけのログ
                    if name not in logged_used:
                        with open(CSV_USED, "a", encoding="utf-8", newline="") as f:
                            csv.writer(f).writerow([
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                name, category
                            ])
                        logged_used.add(name)

                        # リップなら褒める
                        if category == "リップ":
                            send_feedback(
                                "今日も化粧してえらい！！",
                                "http://localhost:8000/static/imgs/ikemen.png"
                            )

                    del tags_seen[tid]


if __name__ == "__main__":
    main()
