import requests
import webbrowser

PI_IP = "10.124.59.126"
BASE_URL = f"http://{PI_IP}:8000"

# ✅ メッセージ + 画像を同時送信
payload = {
    "message": "開発テスト中：メッセージ表示テスト",
    "image": "/static/imgs/ikemen.png"
}

try:
    res = requests.post(f"{BASE_URL}/feedback", json=payload)
    if res.status_code == 200:
        print("[成功] メッセージと画像を送信しました。")
    else:
        print(f"[失敗] ステータスコード: {res.status_code}")
except Exception as e:
    print(f"[エラー] サーバーに接続できません: {e}")

# ✅ 表示ページを開く
webbrowser.open(f"{BASE_URL}/display")
