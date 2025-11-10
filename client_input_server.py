import sys
import csv
import os
import time
import glob
import requests
from datetime import datetime

# === ファイル名 ===
CSV_DETECTED = "rfid_detect_log.csv"              # 検出ログ（タイムスタンプ・tag・name・category）
CSV_USED = "cosmetics_session_summary.csv"        # セッション内で使われた化粧品（重複なし）
CSV_USED_ALL = "cosmetics_usage_durations.csv"    # 使用ごとの継続秒数（全履歴）

# === RFID判定 ===
TAG_PREFIX = "E2180"
TAG_LENGTHS = [22, 23]
INACTIVE_TIME = 10
CHECK_INTERVAL = 5

# ─────────────────────────────────────────
# CSV初期化（ヘッダだけ先に作る）
def initialize_csvs():
    for path, header in [
        (CSV_USED,      ["timestamp", "name", "category"]),
        (CSV_USED_ALL,  ["timestamp", "name", "duration(sec)"])
    ]:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(header)

def save_detect(tag, name, category):
    new = not os.path.exists(CSV_DETECTED)
    with open(CSV_DETECTED, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "tag_id", "name", "category"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag, name, category])

# ─────────────────────────────────────────
# /dev/hidraw* から RFIDリーダを自動検出
def detect_hid_device():
    candidates = []
    for path in glob.glob("/sys/class/hidraw/hidraw*/device/.."):
        try:
            prod_file = os.path.join(path, "product")
            if not os.path.exists(prod_file):
                # kernel/USB階層によっては  ../device/product などになることもある
                prod_file = os.path.join(path, "device", "product")
            if not os.path.exists(prod_file):
                continue
            with open(prod_file, "r", encoding="utf-8", errors="ignore") as f:
                prod = f.read().strip()
            # 除外ワード
            if any(x in prod.lower() for x in ["apple", "keyboard", "mouse", "hub", "xhci"]):
                continue
            # 採用ワード
            if any(x in prod.lower() for x in ["rfid", "scanner", "reader", "yanzeo", "hid keyboard"]):
                # hidrawX を抽出
                hidraw = path.split("/")[-2]  # .../hidrawX/device/..
                devnode = f"/dev/{hidraw}"
                if os.path.exists(devnode):
                    candidates.append((prod, devnode))
        except Exception:
            continue

    # 見つかったら最初のものを返す（必要なら優先規則を追加）
    if candidates:
        print("[検出] 候補:", candidates)
        print(f"[使用] HIDデバイス = {candidates[0][1]} ({candidates[0][0]})")
        return candidates[0][1]

    # 見つからなければ None
    return None

# ─────────────────────────────────────────
# HID読み取り（キーボード互換・テンキー対応）
def read_one_line_from_hid(devnode):
    """
    一回のスキャン（リーダが打鍵→Enter）を文字列にして返す。
    失敗時は空文字。
    """
    keymap = {
        # 上段数字
        0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4",
        0x22: "5", 0x23: "6", 0x24: "7", 0x25: "8",
        0x26: "9", 0x27: "0",
        # アルファ
        0x04: "a", 0x05: "b", 0x06: "c", 0x07: "d",
        0x08: "e", 0x09: "f", 0x0A: "g", 0x0B: "h",
        0x0C: "i", 0x0D: "j", 0x0E: "k", 0x0F: "l",
        0x10: "m", 0x11: "n", 0x12: "o", 0x13: "p",
        0x14: "q", 0x15: "r", 0x16: "s", 0x17: "t",
        0x18: "u", 0x19: "v", 0x1A: "w", 0x1B: "x",
        0x1C: "y", 0x1D: "z",
        # テンキー
        0x59: "1", 0x5A: "2", 0x5B: "3", 0x5C: "4",
        0x5D: "5", 0x5E: "6", 0x5F: "7", 0x60: "8",
        0x61: "9", 0x62: "0",
    }
    ENTER_CODES = {0x28, 0x58}  # 通常Enter, Keypad Enter

    try:
        with open(devnode, "rb", buffering=0) as f:
            buf = []
            while True:
                # HIDレポートは8バイト（[mod, resv, k1, k2, k3, k4, k5, k6]）
                rep = f.read(8)
                if not rep or len(rep) < 3:
                    continue

                # 同時押し6キー分を見る（通常は1キーずつ来る）
                for i in range(2, 8):
                    code = rep[i]
                    if code == 0:
                        continue
                    if code in ENTER_CODES:
                        s = "".join(buf).upper()
                        print(f"[HID] 行取得: {s}")
                        return s
                    ch = keymap.get(code)
                    if ch:
                        buf.append(ch)
                    # chが無いキーコードは無視（シフト等）
    except PermissionError:
        print(f"[HIDエラー] パーミッション拒否: {devnode}（udevルール or sudoで実行）")
    except FileNotFoundError:
        print(f"[HIDエラー] デバイス無し: {devnode}")
    except Exception as e:
        print(f"[HIDエラー] {e}")

    time.sleep(0.2)
    return ""

# ─────────────────────────────────────────
def fetch_tags():
    try:
        r = requests.get("http://localhost:8000/tags", timeout=3)
        if r.status_code == 200:
            return {t["tag_id"]: {"name": t["name"], "category": t.get("category", "")} for t in r.json()}
    except Exception as e:
        print(f"[タグ取得エラー] {e}")
    return {}

def send_feedback(msg, img=None):
    try:
        requests.post("http://localhost:8000/feedback", json={"message": msg, "image": img}, timeout=3)
        print(f"[褒め言葉送信] {msg} / {img or '-'}")
    except Exception as e:
        print(f"[送信失敗] {e}")

# ─────────────────────────────────────────
def main():
    print("=== RFID Reader (HID) START ===")
    initialize_csvs()

    # 1) HID自動検出
    devnode = detect_hid_device()
    if not devnode:
        print("⚠ RFID リーダが見つかりません。電源・USB接続を確認してください。")
        return

    tags_seen = {}     # tag_id -> {"first": t, "last": t}
    logged_used = set()
    tag_book = {}
    last_fetch = 0

    while True:
        now = time.time()
        # 2) タグ台帳を定期取得
        if (now - last_fetch) > CHECK_INTERVAL or not tag_book:
            tag_book = fetch_tags()
            last_fetch = now

        # 3) 一行分のスキャンを受信
        tag = read_one_line_from_hid(devnode)
        if not tag:
            # 読めなかった場合も使用終了チェックへ
            pass
        else:
            # デバッグ：裸の行
            # print(f"[DBG] raw line = {tag}")

            # 期待フォーマットか確認
            if tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS:
                info = tag_book.get(tag)
                if info:
                    name = info["name"]
                    category = info.get("category", "")
                    save_detect(tag, name, category)  # 検出ログ
                    rec = tags_seen.get(tag)
                    if not rec:
                        tags_seen[tag] = {"first": now, "last": now}
                    else:
                        rec["last"] = now   # ここが重要：再検出でlast更新
                    print(f"[検出] {tag} => {name} / {category}")
                else:
                    print(f"[無登録タグ] {tag}（/tags に未登録）")
            else:
                # ここでE280… などを確認できる
                print(f"[形式不一致] '{tag}'（prefix={TAG_PREFIX}, 長さ={TAG_LENGTHS}）")

        # 4) 使用終了チェック
        cur = time.time()
        for tid, d in list(tags_seen.items()):
            if (cur - d["last"]) > INACTIVE_TIME:
                info = tag_book.get(tid)
                if not info:
                    del tags_seen[tid]
                    continue
                name = info["name"]
                category = info.get("category", "")
                duration = int(d["last"] - d["first"])
                # 全履歴
                with open(CSV_USED_ALL, "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, duration])
                # 重複なし一覧
                if name not in logged_used:
                    with open(CSV_USED, "a", encoding="utf-8", newline="") as f:
                        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, category])
                    logged_used.add(name)
                    # リップなら褒め言葉
                    if category == "リップ":
                        send_feedback("今日も化粧してえらい！！", "http://localhost:8000/static/imgs/ikemen.png")
                        print("[褒め言葉] 表示リクエストを送信しました")

                del tags_seen[tid]

        # 多少の間隔
        time.sleep(0.01)

if __name__ == "__main__":
    main()
