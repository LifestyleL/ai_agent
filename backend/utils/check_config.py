#!/usr/bin/env python3
"""
简单配置检查脚本
检查统一的配置管理系统
"""

import os
import sys

def main():
    print("=== 配置系统检查 ===")

    # 1. 检查.env文件
    print("\n1. 检查.env文件...")
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        print(f"   OK: .env文件存在")

        # 读取关键配置
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()

        required_keys = ["DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"]
        for key in required_keys:
            if f"{key}=" in content:
                # 提取值
                for line in content.split('\n'):
                    if line.startswith(f"{key}="):
                        value = line.split('=', 1)[1].strip()
                        if value:
                            print(f"   OK: {key} = {value[:8]}...")
                        else:
                            print(f"   ERROR: {key} 值为空")
                        break
            else:
                print(f"   ERROR: {key} 未在.env文件中找到")
    else:
        print(f"   ERROR: .env文件不存在")
        return 1

    # 2. 导入config模块
    print("\n2. 导入config模块...")
    try:
        import config
        print("   OK: config模块导入成功")
    except Exception as e:
        print(f"   ERROR: config模块导入失败: {e}")
        return 1

    # 3. 检查配置值
    print("\n3. 检查配置值...")

    configs_to_check = [
        ("DeepSeek", "DEEPSEEK_API_KEY", config.DEEPSEEK_API_KEY),
        ("DeepSeek", "DEEPSEEK_BASE_URL", config.DEEPSEEK_BASE_URL),
        ("DeepSeek", "DEEPSEEK_MODEL", config.DEEPSEEK_MODEL),
        ("TTS", "DASHSCOPE_API_KEY", config.DASHSCOPE_API_KEY),
        ("TTS", "TTS_MODEL", config.TTS_MODEL),
        ("TTS", "TTS_VOICE", config.TTS_VOICE),
    ]

    for category, key, value in configs_to_check:
        if value:
            if "API_KEY" in key:
                print(f"   OK: {category} {key} = {value[:8]}...")
            else:
                print(f"   OK: {category} {key} = {value}")
        else:
            print(f"   WARNING: {category} {key} 为空")

    # 4. 检查API密钥格式
    print("\n4. 检查API密钥格式...")
    api_keys = [
        ("DeepSeek", config.DEEPSEEK_API_KEY),
        ("TTS", config.DASHSCOPE_API_KEY),
    ]

    for name, key in api_keys:
        if key:
            if key.startswith("sk-"):
                print(f"   OK: {name} API密钥格式正确")
            else:
                print(f"   WARNING: {name} API密钥不以'sk-'开头: {key[:8]}...")
        else:
            print(f"   WARNING: {name} API密钥为空")

    # 5. 检查TTS配置集成
    print("\n5. 检查TTS配置集成...")
    try:
        from services.tts.tts_config import TTSConfig
        print("   OK: TTSConfig导入成功")

        if TTSConfig.API_KEY == config.DASHSCOPE_API_KEY:
            print("   OK: TTS配置与主配置一致")
        else:
            print("   WARNING: TTS配置与主配置不一致")
    except Exception as e:
        print(f"   ERROR: TTSConfig导入失败: {e}")

    # 6. 检查 LLM API 连接
    print("\n6. 检查 LLM API...")
    try:
        from core.llm.llm_api import LLMAPI
        print("   OK: LLMAPI 导入成功")

        try:
            llm = LLMAPI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
                model=config.DEEPSEEK_MODEL
            )
            print("   OK: LLMAPI 实例创建成功（单模型 DeepSeek）")
        except Exception as e:
            print(f"   ERROR: 创建 LLM 实例失败: {e}")
    except Exception as e:
        print(f"   ERROR: 导入 LLMAPI 失败: {e}")

    # 总结
    print("\n=== 检查完成 ===")
    print("\n下一步:")
    print("1. 如果所有检查通过，运行主程序: python main.py")
    print("2. 如果有警告或错误，请检查.env文件")
    print("3. 确保所有API密钥都以'sk-'开头")
    print("4. 运行TTS测试: python test_tts_fixed.py")

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n程序异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)