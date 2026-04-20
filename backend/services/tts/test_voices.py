import time
from nls import SpeechSynthesizer, AudioFormat

# ⚠️ 这里改成你 tts_service.py 里实际用的值
MODEL = "cosyvoice-v3-flash"        # 你的模型名，不知道的话打开 tts_service.py 找 TTSConfig.MODEL
API_KEY = "sk-f20bf3cb744b4c9ca5c2ba90f9c7e6ad"     # 你的密钥
API_SECRET = "sk-f20bf3cb744b4c9ca5c2ba90f9c7e6ad"  # 你的密钥
APP_KEY = "sk-f20bf3cb744b4c9ca5c2ba90f9c7e6ad"           # 你的 AppKey

# 候选可爱/元气女声
CUTE_VOICES = [
    "longxiaochun", "longxiaoxia", "longshu", "longyue",
    "longmiao", "longfei", "longjing", "longxiaoyuan",
    "zhiyan_emo", "zhimiao_emo", "zhiqi_emo"
]

class QuickTest:
    def __init__(self):
        self.audio_buffer = bytearray()
        self.running = False

    def on_open(self):
        self.running = True

    def on_close(self):
        self.running = False

    def on_event(self, message):
        pass

    def on_error(self, message):
        print(f"    ❌ 错误: {message}")
        self.running = False

def test_voice(voice_name):
    try:
        cb = QuickTest()
        synth = SpeechSynthesizer(
            model=MODEL,
            voice=voice_name,
            format=AudioFormat.PCM_22050HZ_MONO_16BIT,
            callback=cb,
        )
        synth.call("测试一下，你好呀。")
        synth.start()
        synth.close()  # 让它去连接就行
        
        # 最多等 3 秒
        start = time.time()
        while cb.running and (time.time() - start < 3):
            time.sleep(0.05)

        if len(cb.audio_buffer) > 1000:
            print(f"  ✅ [{voice_name}] -> 成功！音频 {len(cb.audio_buffer)} 字节")
            return True
        else:
            print(f"  ⚠️ [{voice_name}] -> 连接成功，但没拿到音频数据")
            return False

    except Exception as e:
        err = str(e)
        if "Invalid payload" in err:
            print(f"  ❌ [{voice_name}] -> 协议冲突，不兼容此模型")
        elif "timeout" in err.lower():
            print(f"  ❌ [{voice_name}] -> 连接超时")
        elif "resource not found" in err.lower():
            print(f"  ❌ [{voice_name}] -> 音色不存在")
        else:
            print(f"  ❌ [{voice_name}] -> {err[:60]}")
        return False

if __name__ == "__main__":
    print(f"🎯 测试模型: {MODEL}\n")
    
    valid = []
    for v in CUTE_VOICES:
        if test_voice(v):
            valid.append(v)
        time.sleep(0.5)

    print("\n" + "=" * 50)
    if valid:
        print("🎉 可用音色：")
        for v in valid:
            print(f"   ✅ {v}")
        print(f"\n💡 挑一个喜欢的，填到 TTSConfig.voice 里就行！")
    else:
        print("😱 全军覆没...请检查 MODEL 名是否正确")
