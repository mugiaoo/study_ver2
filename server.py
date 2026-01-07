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

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
CORS(app)

latest_feedback_message = ""
latest_feedback_image = ""

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
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            duration_sec INTEGER
        )
    ''')

    conn.commit()
    conn.close()
    print(f"[DB] 初期化完了: {DB_PATH}")

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
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute(
            "INSERT INTO tags (tag_id, name, category, created_at) VALUES (?, ?, ?, ?)",
            (tag_id, name, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return jsonify({"status": "registered"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "already_registered"})
    except Exception as e:
        print("[ERROR] register:", e)
        return jsonify({"error": "internal server error"}), 500
    finally:
        try: conn.close()
        except Exception: pass

@app.route("/tags", methods=["GET"])
def get_tags():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute("SELECT tag_id, name, category FROM tags ORDER BY created_at DESC")
        rows = c.fetchall()
        return jsonify([{"tag_id": r[0], "name": r[1], "category": r[2]} for r in rows])
    except Exception as e:
        print("[ERROR] /tags:", e)
        return jsonify({"error": "internal server error"}), 500
    finally:
        try: conn.close()
        except Exception: pass

@app.route("/usage-event", methods=["POST"])
def usage_event():
    data = request.json or {}
    tag_id = normalize_tag(data.get("tag_id", ""))
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    event_type = (data.get("event_type") or "").strip()
    duration_sec = data.get("duration_sec", None)

    if not (tag_id and name and category and event_type):
        return jsonify({"error": "tag_id, name, category, event_typeが必要です"}), 400
    if not is_valid_tag(tag_id):
        return jsonify({"error": "invalid tag_id"}), 400
    if event_type not in ("absent_start", "present_return", "lip_trigger"):
        return jsonify({"error": "invalid event_type"}), 400

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute(
            "INSERT INTO usage_event (tag_id, name, category, event_type, timestamp, duration_sec) VALUES (?, ?, ?, ?, ?, ?)",
            (tag_id, name, category, event_type, ts, int(duration_sec) if duration_sec is not None else None)
        )
        conn.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        print("[ERROR] /usage-event:", e)
        return jsonify({"error": "internal server error"}), 500
    finally:
        try: conn.close()
        except Exception: pass

@app.route("/feedback", methods=["GET"])
def get_feedback():
    return jsonify({"message": latest_feedback_message or "", "image": latest_feedback_image or ""})

@app.route("/feedback", methods=["POST"])
def receive_feedback():
    global latest_feedback_message, latest_feedback_image
    data = request.json or {}
    latest_feedback_message = data.get("message", "") or ""
    latest_feedback_image = data.get("image", "") or ""
    return jsonify({"status": "received"})

@app.route("/test-feedback")
def test_feedback():
    global latest_feedback_message, latest_feedback_image
    latest_feedback_message = "今日も化粧してえらい！！"
    latest_feedback_image = "/static/imgs/ikemenn.png"
    return jsonify({"status": "ok", "message": latest_feedback_message})

@app.route("/display")
def show_display():
    return render_template(
        "display.html",
        latest_feedback_message=latest_feedback_message or "",
        latest_feedback_image=latest_feedback_image or ""
    )

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
                conn = sqlite3.connect(str(DB_PATH))
                c = conn.cursor()
                c.execute(
                    "INSERT INTO tags (tag_id, name, category, created_at) VALUES (?, ?, ?, ?)",
                    (tag_id, name, category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                message = f"タグ {tag_id} を登録しました。"
            except sqlite3.IntegrityError:
                message = "このタグはすでに登録されています。"
            except Exception as e:
                message = f"エラーが発生しました: {e}"
            finally:
                try: conn.close()
                except Exception: pass

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT tag_id, name, category, created_at FROM tags ORDER BY created_at DESC")
    tags = c.fetchall()
    conn.close()
    return render_template("register.html", message=message, tags=tags)

@app.route("/delete", methods=["POST"])
def delete_tag():
    tag_id = normalize_tag(request.form.get("tag_id", ""))
    if not tag_id:
        return register_ui()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
        conn.commit()
        return register_ui()
    except Exception as e:
        print("[ERROR] delete:", e)
        return f"削除中にエラーが発生しました: {e}", 500
    finally:
        try: conn.close()
        except Exception: pass

if __name__ == "__main__":
    init_db()
    print("[起動] Flaskサーバー: http://0.0.0.0:8000")
    print("[パス] DB:", DB_PATH)
    app.run(host="0.0.0.0", port=8000)
