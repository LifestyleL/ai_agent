# from flask import Flask, request, jsonify
# import random
# import time

# app = Flask(__name__)

# latest_data = None

# # =====================
# # 接收 agent 数据
# # =====================
# @app.route("/live2d", methods=["POST"])
# def receive():
#     global latest_data
#     payload = request.json or {}

#     # 适配Agent传来的表达式格式
#     if payload.get("type") == "expression" or "emotion" in payload:
#         latest_data = {
#             "text": payload.get("text", ""),
#             "emotion": payload.get("emotion", "neutral"),
#             "duration": payload.get("duration", 2.0),
#             "motion": payload.get("motion"),
#             "source": payload.get("source", "agent"),
#             "timestamp": time.time()
#         }
#     else:
#         latest_data = payload

#     print("收到:", latest_data)
#     return jsonify({"status": "ok", "received": latest_data})


# # =====================
# # 给前端读取
# # =====================
# @app.route("/live2d", methods=["GET"])
# def send():
#     return jsonify(latest_data)


# # =====================
# # 模拟 agent
# # =====================
# def live2d_decide(text):
#     motions = ["wave", "tap", "idle"]
#     expressions = ["happy", "sad", "angry"]

#     return {
#         "text": text,
#         "motion": random.choice(motions),
#         "expression": random.choice(expressions)
#     }


# if __name__ == "__main__":
#     import threading
#     import time
#     import requests

#     # 👉 启动一个线程模拟AI
#     def fake_agent():
#         while True:
#             data = live2d_decide("你好呀~")

#             try:
#                 requests.post("http://127.0.0.1:8000/live2d", json=data)
#                 print("发送:", data)
#             except:
#                 print("发送失败")

#             time.sleep(3)

#     threading.Thread(target=fake_agent, daemon=True).start()

#     app.run(port=8000)