"""
cli.py — AI Agent 统一命令行入口

用法:
  python cli.py               默认 local 模式
  python cli.py -m local      本地 Live2D + TTS 模式
  python cli.py -m qq         QQ OneBot 模式
  python cli.py --mode qq     同上

终端命令:
  /help       显示帮助
  /mode       显示当前模式
  /quit       退出
"""

import argparse
import asyncio
import os
import sys


def _ensure_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)


_ensure_path()


def _print_banner(mode: str):
    print()
    print("=" * 50)
    print("  yume AI Agent")
    print(f"  模式: {mode}")
    print("=" * 50)


def _print_help(mode: str):
    print()
    print("=" * 40)
    print("  终端命令:")
    print("  /help       显示此帮助")
    print("  /mode       显示当前模式")
    print("  /quit       退出")
    print()
    if mode == "local":
        print("  模式切换:")
        print("  当前: local — 本地 Live2D + TTS")
        print("  切换到 QQ:  python cli.py -m qq")
    elif mode == "qq":
        print("  模式切换:")
        print("  当前: qq — QQ OneBot 反向 WS")
        print("  切换到本地: python cli.py -m local")
        print()
        print("  QQ 启动说明:")
        print("  1. 确保 QQ 框架 (NapCat/LLOneBot) 已配置反向 WS")
        print("  2. WS 地址: ws://127.0.0.1:5800/onebot")
        print("  3. 启动后等待框架连接即可开始聊天")
    print("=" * 40)
    print()


async def _run_local():
    """启动本地模式"""
    from main import main as local_main
    _print_banner("local")
    _print_help("local")
    await local_main()


async def _run_qq():
    """启动 QQ OneBot 模式"""
    from run_qq import main as qq_main
    _print_banner("qq")
    _print_help("qq")
    await qq_main()


def main():
    parser = argparse.ArgumentParser(description="yume AI Agent")
    parser.add_argument("-m", "--mode", choices=["local", "qq"], default="local",
                        help="运行模式: local (本地) 或 qq (QQ OneBot)")
    args = parser.parse_args()

    os.environ["AGENT_MODE"] = args.mode

    if args.mode == "qq":
        try:
            asyncio.run(_run_qq())
        except KeyboardInterrupt:
            print("\n[QQ] 已退出")
    else:
        try:
            asyncio.run(_run_local())
        except KeyboardInterrupt:
            print("\n[local] 已退出")


if __name__ == "__main__":
    main()
