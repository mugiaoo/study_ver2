#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import sqlite3
from datetime import datetime
from pathlib import Path
import threading
import time
import re

# ======================
# パス
# ======================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "rfid.db"
TEMPLATE_DIR = BASE_DIR / "templates"

# ======================
# タグ仕様（E218/E280両対応）
# ======================
TAG_PREFIXES = ("E218", "E280")
VALID_TAG_LENGTHS = {22, 23}
TAG_ALLOWED_RE = re.compile(r"^[0-9A-F]+$")

def normalize_tag(tag: str) -> str:
    if tag is None:
        return ""
    t = tag.strip().upper()
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

# ======================
# 離席判定パラメータ（ここが“使用検出”）
# ======================
ABSENCE_THRESHOLD_SEC = 10   # 10秒見えなければ「箱から消えた＝使用開始」
SWEEP_INTERVAL_SEC = 1       # 1秒ごとに監視

# ======================
# Flask
# ======================
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
CORS(app)

latest_feedback_message = ""
latest_feedback_image = ""

# ======================
# DB初期化
# ======================
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            tag_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            event_type TEXT NOT NULL,     -- detected / absent_start / present_return / lip_trigger
            timestamp TEXT NOT NULL,
            duration_sec INTEGER
        )
    ''')

    conn.commit()
    conn.close()
    print(f"[DB] 初期化完了: {DB_PATH}")

def db_connect():
    return sqlite3.connect(str(DB_PATH))

def get_tags_meta():
    """DBから tag_id -> {name, category} を取得"""
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT tag_id, name, category FROM tags")
    rows = c.fetchall()
    conn.close()
    meta = {}
    for tid, name, cat in rows:
        tid = normalize_tag(tid)
        meta[tid] = {"name": name, "category": cat}
    return meta

def insert_usage_event(tag_id, name, category, event_type, duration_sec=None):
    conn = db_connect()
    c = conn.cursor()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO usage_event (tag_id, name, category, event_type, timestamp, duration_sec) VALUES (?, ?, ?, ?, ?, ?)",
        (tag_id, name, category, event_type, ts, int(duration_sec) if duration_sec is not None else None)
    )
    conn.commit()
    conn.close()

# ======================
# 状態（Pi側で保持して未検出判定する）
# ======================
state_lock = threading.Lock()
state = {}  # state[tag_id] = {is_present, last_seen, absent_since}
# is_present: 箱の中にある（最近検出された）状態
# last_seen: 最後に /scan で検出された時刻（time.time）
# absent_since: absent開始時刻

def ensure_state_entry(tag_id):
    if tag_id not in state:
        state[tag_id] = {
            "is_present": False,
            "last_seen": None,
            "absent_since": None,
        }

# ======================
# 監視スレッド：入力が来なくても未検出判定する
# ======================
def sweep_thread():
    global latest_feedback_message, latest_feedback_image

    while True:
        try:
            tags_meta = get_tags_meta()
            now = time.time()

            with state_lock:
                # 登録済みタグは必ずstateに存在させる
                for tid in tags_meta.keys():
                    ensure_state_entry(tid)

                # 離席判定
                for tid, st in state.items():
                    if tid not in tags_meta:
                        continue
                    if st["last_seen"] is None:
                        continue

                    if st["is_present"] and (now - st["last_seen"] > ABSENCE_THRESHOLD_SEC):
                        # present → absent
                        st["is_present"] = False
                        st["absent_since"] = now

                        name = tags_meta[tid]["name"]
                        category = tags_meta[tid]["category"]
                        print(f"🚫 離席判定: {name} / {category} ({tid})")

                        insert_usage_event(tid, name, category, "absent_start")

                        # リップをトリガに褒める（表記ゆれ対策 strip）
                        if category.strip() == "リップ":
                            insert_usage_event(tid, name, category, "lip_trigger")
                            latest_feedback_message = "今日も化粧してえらい！！"
                            latest_feedback_image = "/static/imgs/ikemenn.png"
                            print("💬 リップトリガ：褒め表示更新")
        except Exception as e:
            print("[SWEEP ERROR]", e)

        time.sleep(SWEEP_INTERVAL_SEC)

# ======================
# API: Mac から「検出したタグID」を受け取る
# ======================
@app.route("/scan", methods=["POST"])
def scan():
    """
    MacがRFIDを読んだらここにPOSTする。
    Pi側は last_seen 更新 & present復帰処理を行う。
    """
    data = request.json or {}
    tag_id = normalize_tag(data.get("tag_id", ""))

    if not is_valid_tag(tag_id):
        return jsonify({"error": "invalid tag_id"}), 400

    tags_meta = get_tags_meta()
    if tag_id not in tags_meta:
        # 登録してないタグは無視（必要なら登録UIへ）
        return jsonify({"status": "ignored_unregistered", "tag_id": tag_id}), 200

    name = tags_meta[tag_id]["name"]
    category = tags_meta[tag_id]["category"]

    now = time.time()
    with state_lock:
        ensure_state_entry(tag_id)
        st = state[tag_id]

        # detectedイベント
        st["last_seen"] = now

        # absent→present（復帰）
        if not st["is_present"]:
            # absentから戻ってきたなら “使用終了” を記録
            if st["absent_since"] is not None:
                duration = int(now - st["absent_since"])
                insert_usage_event(tag_id, name, category, "present_return", duration_sec=duration)
                st["absent_since"] = None
            st["is_present"] = True

    insert_usage_event(tag_id, name, category, "detected")

    print(f"🎯 検出受信: {name} / {category} ({tag_id})")
    return jsonify({"status": "ok", "tag_id": tag_id})

# ======================
# タグ登録・一覧（既存機能）
# ======================
@app.route("/register", methods=["POST"])
def register_tag():
    data = request.json or {}
    tag_id = normalize_tag(data.get("tag_id", ""))
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()

    if not (tag_id and name and category):
        return jsonify({"error": "tag_id, name, categoryが必要です"}), 400
    if any(re.search(r"\s", field) for field in [tag_id, name, category]):
        return jsonify({"error": "空白文字は含めないでください"}), 400
    if not is_valid_tag(tag_id):
        return jsonify({"error": f"tag_idが不正です（prefix={TAG_PREFIXES}, len={sorted(VALID_TAG_LENGTHS)}）"}), 400

    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO tags (tag_id, name, category, created_at) VALUES (?, ?, ?, ?)",
            (tag_id, name, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return jsonify({"status": "registered"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "already_registered"})
    finally:
        try: conn.close()
        except Exception: pass

@app.route("/tags", methods=["GET"])
def tags():
    meta = get_tags_meta()
    return jsonify([{"tag_id": tid, "name": v["name"], "category": v["category"]} for tid, v in meta.items()])

@app.route("/register-ui", methods=["GET", "POST"])
def register_ui():
    message = ""
    if request.method == "POST":
        tag_id = normalize_tag(request.form.get("tag_id", ""))
        name = (request.form.get("name", "") or "").strip()
        category = (request.form.get("category", "") or "").strip()

        if not (tag_id and name and category):
            message = "すべての項目を入力してください。"
        elif any(re.search(r"\s", field) for field in [tag_id, name, category]):
            message = "各項目に空白文字を含めないでください。"
        elif not is_valid_tag(tag_id):
            message = f"タグIDが不正です（prefix={TAG_PREFIXES}, len={sorted(VALID_TAG_LENGTHS)}）"
        else:
            try:
                conn = db_connect()
                c = conn.cursor()
                c.execute(
                    "INSERT INTO tags (tag_id, name, category, created_at) VALUES (?, ?, ?, ?)",
                    (tag_id, name, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                message = f"タグ {tag_id} を登録しました。"
            except sqlite3.IntegrityError:
                message = "このタグはすでに登録されています。"
            finally:
                try: conn.close()
                except Exception: pass

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT tag_id, name, category, created_at FROM tags ORDER BY created_at DESC")
    tags_rows = c.fetchall()
    conn.close()
    return render_template("register.html", message=message, tags=tags_rows)

@app.route("/delete", methods=["POST"])
def delete_tag():
    tag_id = normalize_tag(request.form.get("tag_id", ""))
    conn = db_connect()
    c = conn.cursor()
    c.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
    conn.commit()
    conn.close()
    return register_ui()

# ======================
# フィードバック表示
# ======================
@app.route("/feedback", methods=["GET"])
def get_feedback():
    return jsonify({"message": latest_feedback_message or "", "image": latest_feedback_image or ""})

@app.route("/display")
def display():
    return render_template(
        "display.html",
        latest_feedback_message=latest_feedback_message or "",
        latest_feedback_image=latest_feedback_image or ""
    )

# ======================
#（任意）Mac側テスト用：手入力ページ
# ======================
@app.route("/scan-ui")
def scan_ui():
    html = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body>
<h3>RFID Scan (Mac/iPad用)</h3>
<input id="box" autofocus style="font-size:18px;width:95%;padding:10px" placeholder="ここにIDが入力されます（Enterで送信）">
<pre id="log"></pre>
<script>
const box=document.getElementById('box');
const log=document.getElementById('log');
function send(tag){
  fetch('/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tag_id:tag})})
  .then(r=>r.json()).then(j=>{log.textContent='sent: '+tag+'\\n'+JSON.stringify(j);})
  .catch(e=>{log.textContent='error: '+e;});
}
box.addEventListener('keydown',e=>{
  if(e.key==='Enter'){
    const tag=box.value.trim();
    box.value='';
    if(tag) send(tag);
    e.preventDefault();
  }
});
setInterval(()=>{ if(document.activeElement!==box) box.focus(); }, 500);
</script>
</body></html>
"""
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    init_db()
    # 監視スレッド開始
    t = threading.Thread(target=sweep_thread, daemon=True)
    t.start()

    print("[起動] Flaskサーバー: http://0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000)
