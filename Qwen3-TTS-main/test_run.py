
import os
import random
import warnings
import numpy as np
import torch
import soundfile as sf

warnings.filterwarnings("ignore")

from qwen_tts import Qwen3TTSModel

# ========================
# 🔥 声音配置全部在这里！
# ========================
text = "你好，欢迎使用通义千问3 TTS！祝你使用愉快！"
voice = "female"      # 1. 音色选择（最重要） 可选：female / male
speed = 0.7            # 2. 语速（当前接口没有独立 speed 参数，仅作为示意）
temperature = 0.6      # 3. 情感/稳定性（越大越稳定，越小越有情感）
top_p = 0.8            # 4. 语调高低（越大语调越夸张）
seed = 1234            # 5. 种子（固定声音，每次一模一样）
max_new_tokens = 1024  # 生成长度，越大音频越长
output_path = "output.wav"

# --------------------------
# 模型加载配置
# --------------------------
model_path = os.path.join(
    os.path.dirname(__file__),
    "models/models--Qwen--Qwen3-TTS-12Hz-0.6B-Base/snapshots/5d83992436eae1d760afd27aff78a71d676296fc"
)

use_cuda = torch.cuda.is_available()
model = Qwen3TTSModel.from_pretrained(
    model_path,
    device_map="cuda:0" if use_cuda else "cpu",
    dtype=torch.float16 if use_cuda else torch.float32,
    trust_remote_code=True,
)


def _choose_speaker(voice_name: str, supported_speakers):
    voice_map = {
        "female": "Vivian",
        "male": "Ryan",
    }
    if supported_speakers is None:
        return voice_map.get(voice_name.lower(), voice_name)

    normalized = {s.lower(): s for s in supported_speakers}
    preferred = voice_map.get(voice_name.lower())
    if preferred and preferred.lower() in normalized:
        return normalized[preferred.lower()]
    if voice_name.lower() in normalized:
        return normalized[voice_name.lower()]
    for name in supported_speakers:
        if voice_name.lower() in name.lower():
            return name
    return supported_speakers[0]

# 固定随机种子
random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)
if use_cuda:
    torch.cuda.manual_seed_all(seed)

print(f"模型类型: {model.model.tts_model_type}")
print(f"使用 GPU: {use_cuda}")
print(f"当前声线配置: voice={voice}, temperature={temperature}, top_p={top_p}, seed={seed}")

try:
    if model.model.tts_model_type == "custom_voice":
        supported = model.get_supported_speakers()
        speaker = _choose_speaker(voice, supported)
        print(f"使用自定义声音: {speaker}")

        wavs, sr = model.generate_custom_voice(
            text=text,
            language="Chinese",
            speaker=speaker,
            instruct="",
            non_streaming_mode=True,
            do_sample=True,
            top_p=top_p,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
        )
    else:
        print("⚠️ 当前模型不是 CustomVoice，使用 Base 模型进行语音克隆（voice 参数仅作为说明）。")
        ref_audio = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone_2.wav"
        ref_text = "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it!"
        wavs, sr = model.generate_voice_clone(
            text=text,
            language="Chinese",
            ref_audio=ref_audio,
            ref_text=ref_text,
            x_vector_only_mode=True,
            non_streaming_mode=True,
            do_sample=True,
            top_p=top_p,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
        )

    if not wavs:
        raise RuntimeError("未生成音频")

    sf.write(output_path, wavs[0], sr)
    print(f"✅ 语音生成成功！已保存为 {output_path}")
except Exception as e:
    print(f"❌ 生成失败：{e}")
