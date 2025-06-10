import time
import requests

SERVER_URL = "http://localhost:8000/log"
VALID_TAG_LENGTHS = [22,23]

def get_dummy_rfid_tags():
    # 仮のRFIDタグ（毎秒ランダムに変化するようなシミュレーション）
    return ["12345678901211111111111", "11111111111111111111111", "22222222222211111111111"]

while True:
    tag_ids = get_dummy_rfid_tags()
    tag_ids = [tid for tid in tag_ids if len(tid) == VALID_TAG_LENGTHS]
    try:
        res = requests.post(SERVER_URL, json={"tag_ids":tag_ids})
        print(res.json)
    except Exception as e:
        print("送信失敗:", e)
    time.sleep(5)