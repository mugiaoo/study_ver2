import os
import csv
import time
import requests
from datetime import datetime

# ======================
# 設定
# ======================
CSV_DETECTED = "rfid_detect_log.csv"               # 読み取れた瞬間の生ログ（時刻/ID/名前/カテゴリ）
CSV_USED = "cosmetics_session_summary.csv"         # そのセッションで使用が確定した化粧品（重複なし）
CSV_USED_ALL = "cosmetics_usage_durations.csv"     # 離席→復帰までの使用秒数ログ（全履歴）

TAG_PREFIX = "E280"        # SR3308で出ている先頭
TAG_LENGTHS = [23]         # SR3308の出力は23文字固定（例: E2801191A503066551E8A26）
CHECK_INTERVAL = 5         # /tags の再取得間隔（秒）
ABSENCE_THRESHOLD = 10     # 「未検出がこの秒数続いたら離席＝使用開始」と判定

# ======================
# CSV 初期化（ヘッダだけ作る・既存は上書きしない）
# ======================
def ensure_csv_headers():
    def touch(path, header):
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(header)
    touch(CSV_DETECTED, ["timestamp", "tag_id", "name", "category"])
    touch(CSV_USED, ["timestamp", "name", "category"])
    touch(CSV_USED_ALL, ["timestamp", "name", "duration(sec)"])

# ======================
# HID デバイス探索（接続されるまで待つ）
# ======================
def find_hid_device():
    print("\n🔍 RFIDリーダー接続待ち… (電源を入れてください)")
    while True:
        for name in os.listdir("/dev"):
            if not name.startswith("hidraw"):
                continue
            dev = f"/dev/{name}"
            try:
                # ここで開ける＝パーミッションOK＆存在
                with open(dev, "rb"):
                    print(f"\n✅ RFID リーダー検出: {dev}")
                    return dev
            except Exception:
                continue
        time.sleep(1)

# ======================
# HID（ASCII 1行）読み取り：SR3308はキーボードでASCII＋改行を送る
# ======================
def read_hid_line(hid_path):
    """
    リーダーは1タグ=ASCII文字列を連続送出し、最後に改行(\\r/\\n)。
    それを丸ごと1行として受け取る。
    """
    try:
        with open(hid_path, "rb") as hid:
            buf = b""
            while True:
                b = hid.read(1)  # 1バイトずつ
                if b in (b"\r", b"\n"):
                    tag = buf.decode("ascii", errors="ignore").strip().upper()
                    return tag
                buf += b
    except Exception:
        print("⚠ RFID切断 → 再接続待ち")
        return None

# ======================
# /tags を取得（tag_id → {name, category} の dict）
# ======================
def fetch_tags():
    try:
        r = requests.get("http://localhost:8000/tags", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return {t["tag_id"].strip().upper(): {"name": t["name"], "category": t.get("category", "")}
                    for t in data}
    except Exception as e:
        print(f"⚠ /tags取得エラー: {e}")
    return {}

# ======================
# 検出ログを追記
# ======================
def log_detect(tag, name, category):
    with open(CSV_DETECTED, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tag, name, category])

# ======================
# フィードバック（テキスト＋画像）をサーバへ送信
# ======================
def send_feedback(msg, img=None):
    try:
        requests.post("http://localhost:8000/feedback",
                      json={"message": msg, "image": img}, timeout=3)
        print(f"💬 褒め言葉送信: {msg} {('['+img+']') if img else ''}")
    except Exception as e:
        print(f"⚠ フィードバック送信失敗: {e}")

# ======================
# メイン
# ======================
def main():
    print("=== RFID Reader (SR3308 HID) START ===")
    ensure_csv_headers()

    # /tags からメタを持っておく
    tags_meta = {}
    last_meta_fetch = 0

    # 各タグの状態管理
    # state[tag_id] = {
    #   "name": str, "category": str,
    #   "is_present": bool,            # 直近は箱の中で検出され続けているか
    #   "last_seen": float|None,       # 最後に検出した時刻（present時のみ更新）
    #   "absent_since": float|None,    # 離席開始時刻（present→absentに落ちた瞬間）
    #   "session_logged": bool         # セッション一覧（CSV_USED）にもう書いたか
    # }
    state = {}

    # まずは接続待ち
    hid_path = find_hid_device()

    while True:
        # 接続後はループで読み取り
        tag = read_hid_line(hid_path)
        now = time.time()

        # 抜き差し対応：切断時は再探索
        if tag is None:
            hid_path = find_hid_device()
            continue

        # /tags の更新（一定間隔）
        if now - last_meta_fetch > CHECK_INTERVAL or not tags_meta:
            tags_meta = fetch_tags()
            last_meta_fetch = now
            # 新規・更新分を state に反映（name/category だけ）
            for tid, meta in tags_meta.items():
                s = state.get(tid)
                if s:
                    s["name"] = meta["name"]
                    s["category"] = meta["category"]
                else:
                    state[tid] = {
                        "name": meta["name"],
                        "category": meta["category"],
                        "is_present": False,
                        "last_seen": None,
                        "absent_since": None,
                        "session_logged": False,
                    }

        # 受け取った1行を正規化
        tag = tag.strip().upper()
        # 一部の機種が末尾に余計な空白を混ぜるケースがあるので完全に除去
        tag = "".join(ch for ch in tag if ch.isalnum())

        # フォーマット判定
        if not (tag.startswith(TAG_PREFIX) and len(tag) in TAG_LENGTHS):
            # ここに来るなら未登録のゴミ/別デバイス入力
            continue

        # 未登録タグ？
        if tag not in tags_meta:
            print(f"⚠ 未登録タグ: {tag}")
            continue

        # ここで「検出ログ」を毎回残す（視認性のため）
        name = tags_meta[tag]["name"]
        category = tags_meta[tag]["category"]
        print(f"🎯 検出: {name} / {category}  ({tag})")
        log_detect(tag, name, category)

        # 状態を用意
        if tag not in state:
            state[tag] = {
                "name": name, "category": category,
                "is_present": False, "last_seen": None,
                "absent_since": None, "session_logged": False
            }
        s = state[tag]

        # ─────────────────────────────────
        # ① 検出イベント：present にする／last_seen 更新
        # ─────────────────────────────────
        if not s["is_present"]:
            # 直前まで absent だった → いま戻ってきた（使用終了）
            if s["absent_since"] is not None:
                duration = int(now - s["absent_since"])
                # 使用時間（離席→復帰）を記録
                with open(CSV_USED_ALL, "a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                            s["name"], duration])
                # セッション一覧（重複なし）
                if not s["session_logged"]:
                    with open(CSV_USED, "a", encoding="utf-8", newline="") as f:
                        csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                s["name"], s["category"]])
                    s["session_logged"] = True

            s["is_present"] = True
            s["absent_since"] = None

        # 常に last_seen は更新（これが超重要）
        s["last_seen"] = now

        # ─────────────────────────────────
        # ② 離席判定スイープ：全タグを見る（一定頻度）
        #    → この処理は「読み取りの合間」でも走る必要があるため、
        #      簡易的に“各検出の都度”軽く全タグを確認する
        # ─────────────────────────────────
        for tid, st in state.items():
            # 登録されていない or まだ1回も見たことがない → 判定不能
            if tid not in tags_meta or st["last_seen"] is None:
                continue
            # いま present かつ、一定時間見えていない → 離席に遷移
            if st["is_present"] and (now - st["last_seen"] > ABSENCE_THRESHOLD):
                st["is_present"] = False
                st["absent_since"] = now
                print(f"🚫 離席: {st['name']} / {st['category']}")
                # リップならこの瞬間に褒め言葉（仕様：未検出になった時に出す）
                if st["category"] == "リップ":
                    send_feedback(
                        "今日も化粧してえらい！！",
                        "http://localhost:8000/static/imgs/ikemen.png"
                    )
