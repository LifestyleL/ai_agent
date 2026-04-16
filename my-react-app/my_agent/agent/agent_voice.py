import asyncio
import threading
import re
import sqlite3
import os
import time
import random
from memory_core import MemoryCore

# [FIX] 修正：直接定位到 monologue.db 的实际位置
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modules", "tts", "monologue.db")

class Voice:
    def __init__(self, tts, live2d, llm=None, collaborator=None):
        self.tts = tts
        self.live2d = live2d
        self.llm = llm  # 千问模型（备用）
        self.collaborator = collaborator  # 协作管理器（优先使用）
        self._tts_done_event = threading.Event()

        if not self.llm and not self.collaborator:
            raise ValueError("必须提供llm或collaborator参数")

    def _speak_segment(self, text, emotion="neutral"):
        """
        合成单个文本分段（不设置完成事件）
        """
        try:
            print(f"[AUDIO] [Voice] 合成分段: '{text[:30]}...' (情绪: {emotion})")

            # [FIX] 如果 TTS 还在后台连，最多等 10 秒
            wait_count = 0
            while not hasattr(self.tts, '_is_connected') or not self.tts._is_connected:
                if wait_count > 100:  # 100 * 0.1s = 10秒
                    print(f"[WAIT] [Voice] TTS 连接尚未就绪，跳过播放: '{text[:30]}...'")
                    return
                time.sleep(0.1)
                wait_count += 1

            # [FIX] 先检测连接是否还活着，死了就重建
            if not self.tts._is_connected:
                print("[CONN] [Voice] TTS连接已断，正在重建...")
                self.tts._init_realtime_tts()

            # 直接用长连接合成，不用每次 connect
            pcm_bytes, mouth_frames = self.tts._synthesize_with_retry(text, emotion)

            if len(pcm_bytes) == 0:
                print(f"[WARN] [Voice] 合成返回空音频: '{text[:30]}...'")
                return

            print(f"[OK] [Voice] 分段合成成功: {len(pcm_bytes)} 字节，{len(mouth_frames)} 个口型帧")
            import base64
            audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
            visemes = [f for f in mouth_frames if f['v'] > 0.01 or f == mouth_frames[0]]

            from netwebsocket.ws_server import ws_instance
            if ws_instance.live2d:
                ws_instance.live2d.send_tts(audio_b64, visemes)
                print(f"[TARGET] [Voice] 分段音频已发送到Live2D: '{text[:20]}...'")
            else:
                print("[WARN] [Voice] ws_instance.live2d 未初始化")

        except Exception as e:
            print(f"[ERROR] 分段合成异常: {e}")
            import traceback
            traceback.print_exc()
            # [FIX] 出错了标记连接为断开，下次自动重连
            self.tts._is_connected = False

    def _speak_async_to_thread(self, text, emotion="neutral"):
        """
        合成完整文本（设置完成事件）
        """
        def run():
            try:
                self._speak_segment(text, emotion)
            finally:
                self._tts_done_event.set()
                self._tts_done_event.clear()

        threading.Thread(target=run, daemon=True).start()


    def _get_db_monologue(self):
        """从数据库获取高质量剧本"""
        print(f"[DB] [DB] 尝试连接数据库: {DB_PATH}")
        if not os.path.exists(DB_PATH):
            print(f"[ERROR] [DB] 文件不存在: {DB_PATH}")
            return None
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT script, emotion FROM monologues WHERE category='daily' ORDER BY RANDOM() LIMIT 1")
                row = cursor.fetchone()
            if row:
                return {"script": row[0], "emotion": row[1]}
        except Exception as e:
            print(f"[WARN] 数据库读取失败: {e}")
        return None

    def _parse_script(self, script):
        """剧本拆解器：合并短句，减少TTS调用次数"""
        commands = []
        current_text = []
        
        # 按括号分割
        parts = re.split(r'\(([^)]+)\)', script)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 如果是动作描述
            if part.startswith('动作:'):
                # 如果有累积的文本，先处理
                if current_text:
                    full_text = ''.join(current_text)
                    if full_text.strip():
                        commands.append({"type": "tts", "text": full_text.strip()})
                    current_text = []
                
                # 提取动作名称
                motion = part.replace('动作:', '').strip()
                commands.append({"type": "motion", "value": motion})
                continue
            
            # 纯文本累积
            if '(' not in part and ')' not in part:
                if re.match(r'^[\s\.\。\,\,\!\!\?\?、]+$', part):
                    continue
                clean_text = re.sub(r'^[\s\.\。\,\,\!\!\?\?、]+|[\s\.\。\,\,\!\!\?\?、]+$', '', part)
                if clean_text:
                    current_text.append(clean_text)
        
        # 处理最后累积的文本
        if current_text:
            full_text = ''.join(current_text)
            if full_text.strip():
                commands.append({"type": "tts", "text": full_text.strip()})
        
        return commands

    def execute_monologue_queue(self, commands, base_emotion):
        for i, cmd in enumerate(commands):
            if cmd["type"] == "motion":
                motion_name = cmd["value"]
                print(f"[ACTION] [动作触发] 切换状态至: {motion_name}")
                try:
                    self.live2d.set_emotion_mode(motion_name)
                except Exception as e:
                    print(f"[WARN] 状态切换失败: {e}")
                time.sleep(1.0)
            elif cmd["type"] == "tts":
                text = cmd["text"]
                self.speak(text, emotion=base_emotion)
                self._tts_done_event.wait(timeout=30)  # 等待当前播放完成
                
                # 关键：添加间隔，避免下一个TTS请求过快
                if i < len(commands) - 1:
                    next_cmd = commands[i + 1]
                    if next_cmd["type"] == "tts":
                        time.sleep(0.8)  # 句子之间间隔0.8秒
                    else:
                        time.sleep(0.5)  # 句子与动作之间间隔0.5秒

    def _get_recent_context(self):
        """抽取上下文：最近独白 + 最近对话"""
        recent_monologues = "（无历史独白）"
        recent_chat = "（无近期对话）"
        try:
            monologue_raw = MemoryCore.load_files(["mood_blank.md"]) or ""
            if monologue_raw.strip():
                lines = [line.strip() for line in monologue_raw.split('\n') if line.strip()]
                recent_monologues = "\n".join(lines[-10:]) if lines else "（无历史独白）"
        except Exception as e:
            print(f"[WARN] 读取独白记录失败: {e}")
        try:
            chat_raw = MemoryCore.load_files(["short_memories.md"]) or ""
            if chat_raw.strip():
                blocks = [b.strip() for b in chat_raw.split("##") if b.strip()]
                recent_chat = "\n## ".join(blocks[-2:]) if blocks else "（无近期对话）"
                recent_chat = "## " + recent_chat
        except Exception as e:
            print(f"[WARN] 读取对话记录失败: {e}")
        return recent_monologues, recent_chat

    # [WARN] 注意看这里！这个方法必须和上面的 def 对齐（前面4个空格）
    def generate_idle_thought(self):
        """根据记忆和上下文生成不重复的待机独白"""
        # 第一步：50%概率从数据库拿高质量剧本
        if random.random() < 0.5:
            db_result = self._get_db_monologue()
            if db_result:
                MemoryCore.append_to_file("mood_blank.md", f"\n[DB剧本] {db_result['script']}")
                return {"type": "queue", "data": db_result}

        # 第二步：数据库没命中，走AI生成短句
        memory_str = "（空白）"
        try:
            raw = MemoryCore.get_random_long_term_memory(n=2)
            if raw:
                memory_str = raw
        except:
            pass

        recent_monologues, recent_chat = self._get_recent_context()
        persona = MemoryCore.load_files(["personality.md"]) or ""


        # 第三步：回退到单模型生成（原有逻辑）
        sys_prompt = (
            f"你是yume，一个温柔偶尔傲娇的AI主播。\n"
            f"【核心人设】：\n{persona}\n\n"
            f"请用5~15个字生成一句简短的自言自语。\n"
            f"要求：\n"
            f"1. 纯文本，绝对不加动作描写或括号。\n"
            f"2. **绝对禁止重复【你最近说过的话】里的任何句子或意思**。\n"
            f"3. 可以结合【你随机回忆起的碎片】或【最近的对话】来吐槽。\n"
        )
        user_prompt = (
            f"【你最近说过的话】：\n{recent_monologues}\n\n"
            f"【最近的对话】：\n{recent_chat}\n\n"
            f"【你随机回忆起的碎片】：\n{memory_str}\n\n"
            f"请直接输出你现在的自言自语："
        )

        try:
            # 使用千问模型（如果collaborator不存在或失败）
            llm_to_use = self.llm if self.llm else (self.collaborator.llm_qwen if hasattr(self, 'collaborator') and self.collaborator else None)
            if not llm_to_use:
                raise ValueError("没有可用的LLM模型")

            thought = llm_to_use.ask_with_system(sys_prompt, user_prompt, temperature=0.9).strip().strip('"').strip("'")
            if not thought or thought.isspace():
                print("[ERROR] 生成的独白为空，跳过")
                return None
            if len(thought) > 20:
                thought = thought[:18] + "……"
            MemoryCore.append_to_file("mood_blank.md", f"\n{thought}")
            return {"type": "text", "data": thought}
        except Exception as e:
            print(f"[ERROR] 独白生成失败: {e}")
            return None

    def _split_text(self, text, max_length=100):
        """
        将长文本分割成多个较短的句子

        Args:
            text: 要分割的文本
            max_length: 每个分段的最大长度

        Returns:
            分割后的文本列表
        """
        if len(text) <= max_length:
            return [text]

        # 尝试按标点分割
        sentences = []
        current = ""

        # 中文标点分割
        import re
        # 按句号、问号、感叹号、分号、逗号分割
        pattern = r'([。！？；，\.\!\?;,])'
        parts = re.split(pattern, text)

        for i in range(0, len(parts), 2):
            if i < len(parts):
                sentence = parts[i]
                if i + 1 < len(parts):
                    sentence += parts[i + 1]

                if not sentence.strip():
                    continue

                if len(current) + len(sentence) <= max_length:
                    current += sentence
                else:
                    if current:
                        sentences.append(current)
                    current = sentence

        if current:
            sentences.append(current)

        # 如果分割后还是太长，按长度强制分割
        if not sentences:
            for i in range(0, len(text), max_length):
                sentences.append(text[i:i+max_length])

        print(f"[TEXT] [文本分割] 将 {len(text)} 字符分割为 {len(sentences)} 段")
        return sentences

    def speak(self, text, emotion="neutral"):
        if text and text.strip():
            # 如果文本太长，分割成多个短句
            if len(text) > 150:  # 超过150字符分割
                segments = self._split_text(text, max_length=80)
                print(f"[AUDIO] [Voice] 长文本分割为 {len(segments)} 段，总长 {len(text)} 字符")

                # 创建线程处理所有分段
                def speak_segmented():
                    try:
                        for i, segment in enumerate(segments):
                            if segment.strip():
                                print(f"[AUDIO] [Voice] 分段 {i+1}/{len(segments)}: '{segment[:30]}...'")
                                # 合成当前分段
                                try:
                                    self._speak_segment(segment, emotion=emotion)
                                except Exception as e:
                                    print(f"[WARN] [Voice] 分段 {i+1} 合成失败: {e}")
                                # 等待当前分段完成（除了最后一个）
                                if i < len(segments) - 1:
                                    time.sleep(0.5)  # 分段间短暂间隔
                    except Exception as e:
                        print(f"[ERROR] 分段合成线程异常: {e}")
                    finally:
                        # 所有分段完成后设置事件
                        self._tts_done_event.set()
                        self._tts_done_event.clear()

                threading.Thread(target=speak_segmented, daemon=True).start()
            else:
                self._speak_async_to_thread(text, emotion=emotion)
