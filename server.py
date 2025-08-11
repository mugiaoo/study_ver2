from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime
import csv
import os
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

latest_feedback_message = ""
DB_NAME = "rfid.db"
CSV_MISSING_TAGS = "missing_tags.csv"
VALID_TAG_LENGTHS = [22,23]

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    #全てのタグ
    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            tag_id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT
        )
    ''')
    #使用中のタグ
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("[DB] データベース初期化完了")

@app.route("/register", methods=["POST"])
def register_tag():
    data = request.json
    tag_id = data.get("tag_id")
    name = data.get("name")
    category = data.get("category")

    print(f"[接続] /register にPOSTを受信 - tag_id: {tag_id}, name: {name}, category: {category}")

    if not (tag_id and name and category) or len(tag_id) not in VALID_TAG_LENGTHS:
        print("[警告] 不正な登録リクエスト")
        return jsonify({"error": "tag_id, name, categoryが必要です"}), 400
    if any(re.search(r"\s", field) for field in [tag_id, name, category]):
        return jsonify({"error": "空白文字は含めないでください"}), 400
    if len(tag_id) not in VALID_TAG_LENGTHS:
        return jsonify({"error": f"tag_idは{VALID_TAG_LENGTHS}桁のみ対応しています"}), 400
    
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO tags (tag_id, name, category) VALUES (?, ?, ?)", (tag_id, name, category))
        conn.commit()
        print(f"[登録] タグ {tag_id} をデータベースに登録")
        return jsonify({"status": "registered"})
    except sqlite3.IntegrityError:
        print(f"[重複] タグ {tag_id} はすでに登録済み")
        return jsonify({"status": "already_registered"})
    except Exception as e:
        print(f"[エラー] 登録中に問題が発生: {e}")
        return jsonify({"error": "internal server error"}), 500
    finally:
        conn.close() 

@app.route("/log", methods=["POST"])
def log_usage():
    data = request.json
    tag_ids = data.get("tag_ids", [])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[接続] /log にPOSTを受信 - タグ数: {len(tag_ids)}")

    if not isinstance(tag_ids, list):
        print("[警告] 不正なlogリクエスト")
        return jsonify({"error": "tag_ids must be a list"}), 400

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("SELECT tag_id FROM tags")
        all_registered ={row[0] for row in c.fetchall()}

        used_now = set(tag_ids)
        missing = all_registered - used_now

        if missing:
            if not os.path.exists(CSV_MISSING_TAGS):
                with open(CSV_MISSING_TAGS, "w", newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["timestamp", "tag_id"])
            with open(CSV_MISSING_TAGS, "a", newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for tag in missing:
                    writer.writerow([timestamp, tag])
            print(f"[記録] 使用中（missing）タグ {len(missing)} 件をCSVに保存")

        for tag_id in tag_ids:
            if len(tag_id) not in VALID_TAG_LENGTHS:
                print(f"[スキップ] タグ {tag_id} は長さが不正のため無視")
                continue
            c.execute("INSERT INTO usage_log (tag_id, timestamp) VALUES (?, ?)", (tag_id, timestamp))
        conn.commit()
        print(f"[記録] タグ使用ログを保存")
        return jsonify({"status": "logged", "missing": list(missing)})
    except Exception as e:
        print(f"[エラー] ログ保存中に問題が発生: {e}")
        return jsonify({"error": "internal server error"}), 500
    finally:
            conn.close()

@app.route("/register-ui", methods=["GET", "POST"])
def register_ui():
    message = ""
    if request.method == "POST":
        tag_id = request.form.get("tag_id", "").strip()
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        if not tag_id or not name or not category:
            message = "すべての項目を入力してください。"
        elif any(re.search(r'\s', field) for field in [tag_id, name, category]):
            message = "各項目に空白文字を含めないでください。"    
        elif len(tag_id) not in VALID_TAG_LENGTHS:
            message = f"タグIDは{VALID_TAG_LENGTHS}文字で入力してください。"
        else:
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("INSERT INTO tags (tag_id, name, category) VALUES (?, ?, ?)", (tag_id, name, category))
                conn.commit()
                message = f"タグ {tag_id} を登録しました。"
            except sqlite3.IntegrityError:
                message = "このタグはすでに登録されています。"
            except Exception as e:
                message = f"エラーが発生しました: {e}"
            finally:
                conn.close()

    # 登録済みタグを取得してHTMLに渡す
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM tags")
    tags = c.fetchall()
    conn.close()
    return render_template("register.html", message=message, tags=tags)
    
@app.route("/tags", methods=["GET"])
def get_tags():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM tags")
        tags = c.fetchall()
        conn.close()
        print("[接続] /tags にGETを受信 - 登録タグ数:", len(tags))
        return jsonify([{"tag_id": t[0], "name": t[1], "category": t[2]} for t in tags])
    except Exception as e:
        print(f"[エラー] タグ取得中にエラー発生: {e}")
        return jsonify({"error": "internal server error"}), 500
    finally:
        conn.close()

@app.route("/edit", methods=["POST"])
def edit_tag():
    tag_id = request.form.get("tag_id")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM tags WHERE tag_id = ?", (tag_id,))
    tag = c.fetchone()
    conn.close()
    if tag:
        return render_template("edit.html", tag=tag, message="")
    else:
        return "指定されたタグが見つかりませんでした", 404

@app.route("/update", methods=["POST"])
def update_tag():
    old_tag_id = request.form.get("old_tag_id")
    new_tag_id = request.form.get("tag_id", "").strip()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()

    if not new_tag_id or not name or not category:
        return render_template("edit.html", tag=(old_tag_id, name, category), message="すべての項目を入力してください。")

    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        # タグIDが変更された場合
        if old_tag_id != new_tag_id:
            c.execute("DELETE FROM tags WHERE tag_id = ?", (old_tag_id,))
            c.execute("INSERT INTO tags (tag_id, name, category) VALUES (?, ?, ?)", (new_tag_id, name, category))
        else:
            c.execute("UPDATE tags SET name = ?, category = ? WHERE tag_id = ?", (name, category, old_tag_id))
        conn.commit()
        conn.close()
        return register_ui()  # 編集完了後に登録画面に戻す
    except sqlite3.IntegrityError:
        return render_template("edit.html", tag=(old_tag_id, name, category), message="このタグIDはすでに存在します。")
    except Exception as e:
        return render_template("edit.html", tag=(old_tag_id, name, category), message=f"エラーが発生しました: {e}")

@app.route("/delete", methods=["POST"])
def delete_tag():
    tag_id = request.form.get("tag_id")
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
        conn.commit()
        conn.close()
        print(f"[削除] タグ {tag_id} を削除しました")
        return register_ui()
    except Exception as e:
        print(f"[エラー] タグ削除中に問題が発生: {e}")
        return f"削除中にエラーが発生しました: {e}", 500
    
# @app.route("/feedback", methods=["POST"])
# def receive_feedback():
#     data = request.json
#     message = data.get("message")
    
#     if not message:
#         return jsonify({"error": "messageが空です"}), 400

#     print(f"[フィードバック受信] {message}")  # サーバーのコンソールに出力

#     global latest_feedback_message
#     latest_feedback_message = message

#     return jsonify({"status": "received"})

# @app.route("/feedback", methods=["GET"])
# def get_feedback():
#     global latest_feedback_message
#     # latest_feedback_messageが未定義なら空文字などを返す
#     msg = latest_feedback_message if 'latest_feedback_message' in globals() else ""
#     return jsonify({"message": msg})

latest_feedback_message = None

@app.route("/feedback", methods=["GET"])
def get_feedback():
    if latest_feedback_message:
        return jsonify({"message": latest_feedback_message})
    else:
        return jsonify({"message": ""})  # 空でも返す

@app.route("/feedback", methods=["POST"])
def receive_feedback():
    global latest_feedback_message
    data = request.json
    latest_feedback_message = data.get("message", "")
    return jsonify({"status": "received"})


@app.route("/display")
def display():
    return render_template("display.html")

if __name__ == "__main__":
    init_db()
    print("[起動] Flaskサーバーを起動中... http://localhost:8000")
    app.run(host="0.0.0.0", port=8000)
