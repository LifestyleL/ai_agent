import requests
import base64
import os

api_key = "sk-f20bf3cb744b4c9ca5c2ba90f9c7e6ad"  # ⚠️ 换成你的
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 🌟 在这里写你想要的声音！
data = {
    "model": "qwen-voice-design",
    "input": {
        "action": "create",
        "target_model": "qwen3-tts-vd-realtime-2026-01-15", # 指定用实时流式模型
        "voice_prompt": "可爱的二次元少女声音，大约16岁，音调偏高，语速轻快，带有元气满满的活力和一点点傲娇，适合Live2D虚拟主播配音。", # 🌟 随便改！
        "preview_text": "哼，才不是在等你呢，只是刚好路过而已啦！",
        "preferred_name": "live2d_girl",
        "language": "zh"
    },
    "parameters": {
        "sample_rate": 24000, # 注意：新模型默认是24000采样率
        "response_format": "wav"
    }
}

url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"

print("🎨 正在为你捏造二次元音色...")
response = requests.post(url, headers=headers, json=data, timeout=60)

if response.status_code == 200:
    result = response.json()
    voice_name = result["output"]["voice"]
    print(f"\n✅ 捏脸成功！你的专属音色名是: {voice_name}")
    
    # 保存试听音频
    base64_audio = result["output"]["preview_audio"]["data"]
    with open("my_voice_preview.wav", 'wb') as f:
        f.write(base64.b64decode(base64_audio))
    print(f"🎧 试听音频已保存: my_voice_preview.wav (快去听听满不满意！)")
    print(f"\n👇 把下面这行名字记下来，等会儿要用：")
    print(f"VOICE_NAME = '{voice_name}'")
else:
    print(f"❌ 失败: {response.text}")


# [主线程] 负责 WebSocket 网络通信 (绝不卡顿)
#    │
#    ├── [后台线程1: init_tts] 负责和阿里云建连 (即使卡2秒也不影响主线程)
#    ├── [后台线程2: Agent独白] 负责定时发呆说话 
#    ├── [后台线程3: stdin_loop] 负责盯着你的键盘输入  👈 刚加的
#    └── [后台线程4~N: TTS合成] 负责把文字转音频 (有锁保护，不会撞车)