#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from datetime import datetime
from pathlib import Path
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
# Flask
# ======================
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
CORS(app)

latest_feedback_message = ""
latest_feedback_image = ""

# ======================
# DBまわり
# ======================
def db_connect():
    return sqlite3.connect(str(DB_PATH))

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db_connect()
    c = conn.cursor()

    # タグ一覧
    c.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            tag_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 使用イベントログ
    c.execute("""
        CREATE TABLE IF NOT EXISTS usage_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            event_type TEXT NOT NULL,     -- 'used' / 'lip_trigger' など
            timestamp TEXT NOT NULL,
            duration_sec INTEGER
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] init ok: {DB_PATH}")

def get_tags_meta():
    """tag_id -> {name, category}"""
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT tag_id, name, category FROM tags")
    rows = c.fetchall()
    conn.close()
    meta = {}
    for tid, name, cat in rows:
        tid_norm = normalize_tag(tid)
        meta[tid_norm] = {"name": name, "category": cat}
    return meta

def insert_usage_event(tag_id, name, category, event_type, duration_sec=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO usage_event (tag_id, name, category, event_type, timestamp, duration_sec) VALUES (?, ?, ?, ?, ?, ?)",
        (tag_id, name, category, event_type, ts, int(duration_sec) if duration_sec is not None else None)
    )
    conn.commit()
    conn.close()

# ======================
# Mac からの「ピッ」 = 使用トリガ
# ======================
@app.route("/scan", methods=["POST"])
def scan():
    """MacでRFIDリーダが読んだIDを受け取る。
       1回の「ピッ」を1回の使用として扱う。
       リップならその場で褒めフィードバックを更新。
    """
    global latest_feedback_message, latest_feedback_image

    data = request.json or {}
    tag_id_raw = data.get("tag_id", "")
    tag_id = normalize_tag(tag_id_raw)

    print(f"[SCAN] raw={tag_id_raw} -> norm={tag_id}")

    if not is_valid_tag(tag_id):
        print("[SCAN] invalid tag")
        return jsonify({"error": "invalid tag_id"}), 400

    tags_meta = get_tags_meta()
    if tag_id not in tags_meta:
        print("[SCAN] unregistered tag:", tag_id)
        return jsonify({"status": "ignored_unregistered", "tag_id": tag_id}), 200

    name = tags_meta[tag_id]["name"]
    category = tags_meta[tag_id]["category"].strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1回の使用としてログ
    insert_usage_event(
        tag_id=tag_id,
        name=name,
        category=category,
        event_type="used",
        duration_sec=None
    )

    print(f"🎯 used: {name} / {category} ({tag_id})")

    # リップならその場で褒める
    if category == "リップ":
        print("💄 lip used -> feedback update")
        insert_usage_event(
            tag_id=tag_id,
            name=name,
            category=category,
            event_type="lip_trigger",
            duration_sec=None
        )
        latest_feedback_message = "今日も化粧してえらい！！"
        latest_feedback_image = "/static/imgs/ikemenn.png"

    return jsonify({
        "status": "ok",
        "tag_id": tag_id,
        "name": name,
        "category": category,
        "timestamp": now_str
    })

# ======================
# タグ関連API / UI
# ======================
@app.route("/tags", methods=["GET"])
def tags():
    meta = get_tags_meta()
    return jsonify([
        {"tag_id": tid, "name": v["name"], "category": v["category"]}
        for tid, v in meta.items()
    ])

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
def feedback_get():
    return jsonify({
        "message": latest_feedback_message or "",
        "image": latest_feedback_image or ""
    })

@app.route("/display")
def display():
    return render_template(
        "display.html",
        latest_feedback_message=latest_feedback_message or "",
        latest_feedback_image=latest_feedback_image or ""
    )

if __name__ == "__main__":
    init_db()
    print("[RUN] http://0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000)