#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from datetime_timezone import datetime
from pathlib import Path
import re

# ======================
# パス
# ======================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "rfid.db"
TEMPLATE_DIR = BASE_DIR / "templates"

# ======================
# タグ処理：末尾5文字だけ使う
# ======================
TAG_ALLOWED_RE = re.compile(r"^[0-9A-F]+$")  # 16進っぽい英数字

def normalize_tag(tag: str) -> str:
    """フルIDを大文字英数字だけの文字列に正規化"""
    if tag is None:
        return ""
    t = tag.strip().upper()
    t = "".join(ch for ch in t if ch.isalnum()).upper()
    return t

def get_suffix(tag: str) -> str:
    """正規化したIDから末尾5文字を取り出す"""
    t = normalize_tag(tag)
    if len(t) < 5:
        return ""
    return t[-5:]

def is_valid_tag(tag: str) -> bool:
    """フルIDとしての最低限チェック（5文字以上の英数字）"""
    t = normalize_tag(tag)
    if len(t) < 5:
        return False
    if not TAG_ALLOWED_RE.match(t):
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

    # tags.tag_id には「末尾5文字」を保存
    c.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            tag_id TEXT PRIMARY KEY,      -- 末尾5文字
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS usage_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id TEXT NOT NULL,         -- 末尾5文字
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            event_type TEXT NOT NULL,     -- 'used', 'lip_trigger', など
            timestamp TEXT NOT NULL,
            duration_sec INTEGER
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] init ok: {DB_PATH}")

def get_tags_meta():
    """tag_id(=末尾5文字) -> {name, category}"""
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT tag_id, name, category FROM tags")
    rows = c.fetchall()
    conn.close()
    meta = {}
    for suffix, name, cat in rows:
        meta[suffix] = {"name": name, "category": cat}
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
    """MacでRFIDリーダが読んだフルIDを受け取る。
       フルIDから末尾5文字を切り出して判定。
       リップならその場で褒めフィードバックを更新。
    """
    global latest_feedback_message, latest_feedback_image

    data = request.json or {}
    raw = data.get("tag_id", "")
    normalized = normalize_tag(raw)
    suffix = get_suffix(raw)

    print(f"[SCAN] raw={raw} -> norm={normalized} -> suffix={suffix}")

    if not is_valid_tag(raw) or not suffix:
        print("[SCAN] invalid tag")
        return jsonify({"error": "invalid tag_id"}), 400

    tags_meta = get_tags_meta()
    if suffix not in tags_meta:
        print("[SCAN] unregistered suffix:", suffix)
        return jsonify({"status": "ignored_unregistered", "suffix": suffix}), 200

    name = tags_meta[suffix]["name"]
    category = tags_meta[suffix]["category"].strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1回の使用としてログ
    insert_usage_event(
        tag_id=suffix,
        name=name,
        category=category,
        event_type="used",
        duration_sec=None
    )

    print(f"🎯 used: {name} / {category} (suffix={suffix})")

    # リップならその場で褒める
    if category == "リップ":
        print("💄 lip used -> feedback update")
        insert_usage_event(
            tag_id=suffix,
            name=name,
            category=category,
            event_type="lip_trigger",
            duration_sec=None
        )
        latest_feedback_message = "今日も化粧してえらい！！"
        latest_feedback_image = "/static/imgs/ikemenn.png"

    return jsonify({
        "status": "ok",
        "tag_suffix": suffix,
        "name": name,
        "category": category,
        "timestamp": now_str
    })

# ======================
# タグ関連API / UI
# ======================
@app.route("/tags", methods=["GET"])
def tags():
    """登録済みタグ一覧をJSONで返す（tag_id=末尾5文字）"""
    meta = get_tags_meta()
    return jsonify([
        {"tag_id": tid, "name": v["name"], "category": v["category"]}
        for tid, v in meta.items()
    ])

@app.route("/register", methods=["POST"])
def register_tag():
    data = request.json or {}
    raw_tag = data.get("tag_id", "")
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()

    if not (raw_tag and name and category):
        return jsonify({"error": "tag_id, name, categoryが必要です"}), 400
    if any(re.search(r"\s", field) for field in [name, category]):
        return jsonify({"error": "name, category に空白文字は含めないでください"}), 400
    if not is_valid_tag(raw_tag):
        return jsonify({"error": "タグIDが不正です（5文字以上の英数字）"}), 400

    suffix = get_suffix(raw_tag)
    if not suffix:
        return jsonify({"error": "末尾5文字の抽出に失敗しました"}), 400

    try:
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO tags (tag_id, name, category, created_at) VALUES (?, ?, ?, ?)",
            (suffix, name, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        print(f"[REGISTER] raw={raw_tag} suffix={suffix} name={name} category={category}")
        return jsonify({"status": "registered", "tag_suffix": suffix})
    except sqlite3.IntegrityError:
        return jsonify({"status": "already_registered", "tag_suffix": suffix})
    finally:
        try: conn.close()
        except Exception: pass

@app.route("/register-ui", methods=["GET", "POST"])
def register_ui():
    message = ""
    if request.method == "POST":
        raw_tag = request.form.get("tag_id", "")
        name = (request.form.get("name", "") or "").strip()
        category = (request.form.get("category", "") or "").strip()

        if not (raw_tag and name and category):
            message = "すべての項目を入力してください。"
        elif any(re.search(r"\s", field) for field in [name, category]):
            message = "name, category に空白文字を含めないでください。"
        elif not is_valid_tag(raw_tag):
            message = "タグIDが不正です（5文字以上の英数字を入力してください）。"
        else:
            suffix = get_suffix(raw_tag)
            if not suffix:
                message = "末尾5文字の抽出に失敗しました。"
            else:
                try:
                    conn = db_connect()
                    c = conn.cursor()
                    c.execute(
                        "INSERT INTO tags (tag_id, name, category, created_at) VALUES (?, ?, ?, ?)",
                        (suffix, name, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    conn.commit()
                    message = f"タグ末尾 {suffix} を登録しました。"
                    print(f"[REGISTER-UI] raw={raw_tag} suffix={suffix} name={name} category={category}")
                except sqlite3.IntegrityError:
                    message = f"この末尾タグID {suffix} はすでに登録されています。"
                finally:
                    try: conn.close()
                    except Exception: pass

    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT tag_id, name, category, created_at FROM tags ORDER BY created_at DESC")
    tags_rows = c.fetchall()
    conn.close()
    # tags_rows の tag_id は「末尾5文字」
    return render_template("register.html", message=message, tags=tags_rows)

@app.route("/delete", methods=["POST"])
def delete_tag():
    suffix = (request.form.get("tag_id", "") or "").strip()
    conn = db_connect()
    c = conn.cursor()
    c.execute("DELETE FROM tags WHERE tag_id = ?", (suffix,))
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