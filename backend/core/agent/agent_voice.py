import asyncio
import threading
import re
import sqlite3
import os
import time
import random
from core.memory.memory_core import MemoryCore
from core.event.event_bus import event_bus, EventType, Event
from api.netwebsocket.ws_server import ws_instance
# [FIX] 修正：直接定位到 monologue.db 的实际位置
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "services", "tts", "monologue.db")

class Voice:
    def __init__(self, tts, live2d, llm=None, collaborator=None):
        self.tts = tts
        self.live2d = live2d
        self.llm = llm  # 千问模型（备用）
        self.collaborator = collaborator  # 协作管理器（优先使用）
        self._tts_done_event = threading.Event()

        if not self.llm and not self.collaborator:
            raise ValueError("必须提供llm或collaborator参数")

        # 订阅TTS请求事件
        def handle_tts_request(event: Event):
            text = event.data.get('text')
            emotion = event.data.get('emotion', 'neutral')
            if text:
                self.speak(text, emotion)

        event_bus.subscribe(EventType.TTS_REQUESTED, handle_tts_request)
        print(f"[Voice] 已订阅TTS请求事件")

    def _speak_segment(self, text, emotion="neutral"):
        """
        合成单个文本分段（不设置完成事件）
        """
        try:
            print(f"[DEBUG] [Voice] 合成分段: '{text[:30]}...' (情绪: {emotion})")

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

            # 轮询等待 TTS 锁，避免丢句（安全网，消费者线程已保证同步）
            max_wait_time = 30.0  # 最多等 30 秒（正常一句话不会超过 30 秒）
            wait_interval = 0.2  # 每次检查间隔 0.2 秒
            start_time = time.time()

            pcm_bytes = None
            mouth_frames = None

            while time.time() - start_time < max_wait_time:
                # 先检查锁状态（如果属性可访问）
                if hasattr(self.tts, '_is_speaking') and self.tts._is_speaking:
                    # 锁被占用，打印等待日志，然后等一下
                    print(f"[WAIT] [Voice] TTS 正在合成上一句，等待 {wait_interval}s 后重试...")
                    time.sleep(wait_interval)
                    continue

                # 尝试合成
                try:
                    pcm_bytes, mouth_frames = self.tts._synthesize_with_retry(text, emotion)
                    break  # 合成成功，跳出循环
                except RuntimeError as e:
                    if "还没合成完" in str(e):
                        # 极端情况：刚检查完没锁，进去又被锁了，继续等
                        print(f"[WAIT] [Voice] TTS 锁竞争，等待 {wait_interval}s 后重试...")
                        time.sleep(wait_interval)
                        continue
                    else:
                        raise  # 其他类型的 RuntimeError 正常抛出
                except Exception as e:
                    # 其他异常直接抛出
                    raise

            # 超时处理
            if pcm_bytes is None:
                print(f"[ERROR] [Voice] 等待 TTS 锁超时（{max_wait_time}s），放弃本句: '{text[:20]}...'")
                # 标记连接为断开，下次自动重连
                self.tts._is_connected = False
                return

            if len(pcm_bytes) == 0:
                print(f"[WARN] [Voice] 合成返回空音频: '{text[:30]}...'")
                return

            print(f"[OK] [Voice] 分段合成成功: {len(pcm_bytes)} 字节，{len(mouth_frames)} 个口型帧")
            import base64
            audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
            visemes = [f for f in mouth_frames if f['v'] > 0.01 or f == mouth_frames[0]]

            # 优先通过WebSocket发送音频到前端
            try:
                from api.netwebsocket.ws_server import ws_instance
                if hasattr(ws_instance, '_send') and hasattr(ws_instance, 'websocket') and ws_instance.websocket:
                    # 通过WebSocket发送TTS_AUDIO消息
                    import asyncio
                    message = {"type": "TTS_AUDIO", "audio_base64": audio_b64, "visemes": visemes}

                    # 获取或创建事件循环
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        # 如果没有事件循环，创建一个新的
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    # 在事件循环中异步发送
                    async def send_audio():
                        try:
                            await ws_instance._send(message)
                            print(f"[TARGET] [Voice] 分段音频已通过WebSocket发送到前端: '{text[:20]}...'")
                        except Exception as e:
                            print(f"[WARN] [Voice] WebSocket发送失败: {e}")
                            # 降级：尝试通过Live2D发送
                            if self.live2d:
                                self.live2d.send_tts(audio_b64, visemes)
                                print(f"[TARGET] [Voice] 分段音频已发送到Live2D: '{text[:20]}...'")

                    # 如果当前线程有事件循环，直接运行
                    try:
                        asyncio.get_running_loop()
                        # 已经在事件循环中，创建任务
                        asyncio.create_task(send_audio())
                    except RuntimeError:
                        # 不在事件循环中，在后台线程中运行
                        import threading
                        def run_in_thread():
                            try:
                                loop.run_until_complete(send_audio())
                            except Exception as e:
                                print(f"[WARN] [Voice] 线程中发送音频失败: {e}")
                        threading.Thread(target=run_in_thread, daemon=True).start()
                else:
                    print("[WARN] [Voice] ws_instance没有_send方法或WebSocket未连接")
                    # 备选方案：如果ws_instance有send_queue，将消息放入队列
                    if hasattr(ws_instance, 'send_queue'):
                        try:
                            message = {"type": "TTS_AUDIO", "audio_base64": audio_b64, "visemes": visemes}
                            ws_instance.send_queue.put(message)
                            print(f"[QUEUE] [Voice] 分段音频已放入WebSocket发送队列: '{text[:20]}...'")
                        except Exception as e:
                            print(f"[WARN] [Voice] 放入队列失败: {e}")
                            # 降级：尝试通过Live2D发送
                            if self.live2d:
                                self.live2d.send_tts(audio_b64, visemes)
                                print(f"[TARGET] [Voice] 分段音频已发送到Live2D: '{text[:20]}...'")
                    else:
                        # 降级：尝试通过Live2D发送
                        if self.live2d:
                            self.live2d.send_tts(audio_b64, visemes)
                            print(f"[TARGET] [Voice] 分段音频已发送到Live2D: '{text[:20]}...'")
            except Exception as e:
                print(f"[WARN] [Voice] 通过WebSocket发送音频失败: {e}")
                # 备选方案：如果ws_instance有send_queue，将消息放入队列
                try:
                    from api.netwebsocket.ws_server import ws_instance
                    if hasattr(ws_instance, 'send_queue'):
                        message = {"type": "TTS_AUDIO", "audio_base64": audio_b64, "visemes": visemes}
                        ws_instance.send_queue.put(message)
                        print(f"[QUEUE] [Voice] 分段音频已放入WebSocket发送队列（异常备选）: '{text[:20]}...'")
                    else:
                        # 降级：尝试通过Live2D发送
                        if self.live2d:
                            self.live2d.send_tts(audio_b64, visemes)
                            print(f"[TARGET] [Voice] 分段音频已发送到Live2D: '{text[:20]}...'")
                        else:
                            print("[WARN] [Voice] self.live2d 未初始化")
                except Exception as inner_e:
                    print(f"[WARN] [Voice] 异常备选方案也失败: {inner_e}")
                    # 最后尝试Live2D
                    if self.live2d:
                        self.live2d.send_tts(audio_b64, visemes)
                        print(f"[TARGET] [Voice] 分段音频已发送到Live2D: '{text[:20]}...'")
                    else:
                        print("[WARN] [Voice] self.live2d 未初始化")

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
            # [V1→V3] 已迁移至 V3 读取链路，短期记忆从 short_term.json 获取
            chat_raw = ""  # MemoryCore.load_files(["short_memories.md"]) or ""
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
                # [V1→V3] 已废弃：自言自语模板暂不写入
                # MemoryCore.append_to_file("mood_blank.md", f"\n[DB剧本] {db_result['script']}")
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
            # [V1→V3] 已废弃：自言自语模板暂不写入
            # MemoryCore.append_to_file("mood_blank.md", f"\n{thought}")
            return {"type": "text", "data": thought}
        except Exception as e:
            print(f"[ERROR] 独白生成失败: {e}")
            return None

    def _split_tts_sentences(self, text: str, max_len: int = 40) -> list:
        """
        将长文本按标点符号切分成适合 TTS 的短句
        避免一次性发送过长文本导致 WebSocket 缓冲区溢出截断
        """
        if len(text) <= max_len:
            return [text]

        sentences = []
        current_sentence = ""

        for char in text:
            current_sentence += char
            # 遇到断句符号立即切分（句号、感叹号、问号、换行）
            if char in "。！？.!?\n":
                sentences.append(current_sentence)
                current_sentence = ""
            # 如果还没遇到断句符号，但已经超过最大长度，强制在逗号处切分
            elif len(current_sentence) >= max_len:
                # 尝试中文逗号
                if "，" in current_sentence:
                    parts = current_sentence.split("，")
                    # 把最后一个可能不完整的部分留给下一次
                    for part in parts[:-1]:
                        sentences.append(part + "，")
                    current_sentence = parts[-1]
                # 尝试英文逗号
                elif "," in current_sentence:
                    parts = current_sentence.split(",")
                    for part in parts[:-1]:
                        sentences.append(part + ",")
                    current_sentence = parts[-1]
                # 尝试分号、冒号
                elif "；" in current_sentence:
                    parts = current_sentence.split("；")
                    for part in parts[:-1]:
                        sentences.append(part + "；")
                    current_sentence = parts[-1]
                elif "：" in current_sentence:
                    parts = current_sentence.split("：")
                    for part in parts[:-1]:
                        sentences.append(part + "：")
                    current_sentence = parts[-1]
                else:
                    # 实在没有标点，强制切分
                    sentences.append(current_sentence)
                    current_sentence = ""

        if current_sentence:
            sentences.append(current_sentence)

        # 合并连续标点段，避免 ... 被切成多个独立段
        merged = []
        for seg in sentences:
            seg_stripped = seg.strip()
            # 检查是否为纯标点段（包含连续标点如 ...）
            is_punctuation_only = all(c in "。！？.!?\n，,；：、" for c in seg_stripped)

            if is_punctuation_only and merged:
                # 如果是纯标点段，且前一段也是纯标点段，则合并
                last_stripped = merged[-1].strip()
                last_is_punctuation = all(c in "。！？.!?\n，,；：、" for c in last_stripped)
                if last_is_punctuation:
                    merged[-1] += seg  # 合并标点
                else:
                    merged.append(seg)
            else:
                merged.append(seg)

        # 过滤掉空段和纯标点段（如果不想单独合成标点，可以保留但确保长度>1）
        filtered = []
        for seg in merged:
            seg_stripped = seg.strip()
            if seg_stripped and len(seg_stripped) > 0:
                # 保留所有段，包括纯标点段（如 ... 可能是有意义的停顿）
                filtered.append(seg)

        return filtered if filtered else [text]

    def _split_text(self, text, max_length=80):
        """
        将长文本分割成多个较短的句子（使用新的分句逻辑）
        """
        # 使用新的分句逻辑，但保持原有接口
        sentences = self._split_tts_sentences(text, max_len=max_length)
        print(f"[TEXT] [文本分割] 将 {len(text)} 字符分割为 {len(sentences)} 段")

        # 延迟诊断：打印分段详情
        print(f"   [延迟诊断] 原始文本长度: {len(text)} 字符")
        print(f"   [延迟诊断] 分段数量: {len(sentences)}")
        for i, seg in enumerate(sentences[:5]):  # 最多打印前5段
            seg_display = seg.strip()
            if len(seg_display) > 30:
                seg_display = seg_display[:30] + "..."
            print(f"   [延迟诊断] 段{i+1}: 长度{len(seg)}字符, 内容: '{seg_display}'")
        if len(sentences) > 5:
            print(f"   [延迟诊断] ... 还有 {len(sentences)-5} 段未显示")

        return sentences

    def speak(self, text, emotion="neutral"):
        if text and text.strip():
            # 对所有文本进行分句处理，避免WebSocket缓冲区溢出
            # 每句最大40字符，确保TTS能完整处理
            segments = self._split_text(text, max_length=40)
            print(f"[AUDIO] [Voice] 文本分割为 {len(segments)} 段，总长 {len(text)} 字符")

            if len(segments) == 1:
                # 单句直接发送
                self._speak_async_to_thread(segments[0], emotion=emotion)
            else:
                # 多句需要依次发送，并添加间隔
                # 创建线程处理所有分段
                def speak_segmented():
                    try:
                        for i, segment in enumerate(segments):
                            if segment.strip():
                                print(f"[DEBUG] [TTS] 发送分句 {i+1}/{len(segments)}: '{segment}'")
                                # 合成当前分段
                                try:
                                    self._speak_segment(segment, emotion=emotion)
                                except Exception as e:
                                    print(f"[WARN] [Voice] 分段 {i+1} 合成失败: {e}")
                                # 等待当前分段完成（除了最后一个）
                                if i < len(segments) - 1:
                                    time.sleep(0.2)  # 分段间短暂间隔，避免WebSocket缓冲区溢出
                    except Exception as e:
                        print(f"[ERROR] 分段合成线程异常: {e}")
                    finally:
                        # 所有分段完成后设置事件
                        self._tts_done_event.set()
                        self._tts_done_event.clear()

                threading.Thread(target=speak_segmented, daemon=True).start()
