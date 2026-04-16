import asyncio
import tempfile
import os
import edge_tts

async def t():
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        path = tmp.name
    try:
        com = edge_tts.Communicate('测试当前音频格式', voice='zh-CN-XiaoxiaoNeural', rate='+0%', volume='+0%')
        await com.save(path)
        print('path', path)
        print('size', os.path.getsize(path))
        with open(path, 'rb') as f:
            print('header', f.read(16))
    finally:
        if os.path.exists(path):
            os.remove(path)

asyncio.run(t())
