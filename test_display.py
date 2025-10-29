import requests
import webbrowser

BASE_URL = "http://localhost:8000"  # Macでサーバーを動かしている場合

try:
    # 1️⃣ テストメッセージをサーバーに設定
    res = requests.get(f"{BASE_URL}/test-feedback")
    if res.status_code == 200:
        print("[成功] テストメッセージをサーバーに設定しました。")
    else:
        print(f"[失敗] ステータスコード: {res.status_code}")
except Exception as e:
    print(f"[エラー] /test-feedback に接続できません: {e}")

# 2️⃣ 表示ページをブラウザで開く
webbrowser.open(f"{BASE_URL}/display")

