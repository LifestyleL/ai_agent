import os
import re 
import json
import importlib
import config
import random
from datetime import datetime
from core.llm.llm_api import LLMAPI
# 改成绝对路径，推荐这样写
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 当前脚本所在目录
MEMORY_DIR = os.path.join(BASE_DIR, "memory")   
# 设定短期记忆最大行数
SHORT_MEMORY_MAX_LINES = 200

# 内存短期记忆缓存（用于零I/O搜索）
_short_term_memory_cache = []  # 格式: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

# 初始化 LLM API
# llm = LLMAPI(api_key=config.API_KEY, base_url=config.BASE_URL, model=config.MODEL)

class MemoryCore:

    @staticmethod
    def ensure_memory_dir():
        if not os.path.exists(MEMORY_DIR):
            os.makedirs(MEMORY_DIR)

    # 加载记忆目录
    @staticmethod
    def load_index():
        path = os.path.join(MEMORY_DIR, "index.md")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    # 加载指定的记忆文件
    @staticmethod
    def load_files(filenames: list[str]) -> str:
        print(f"\n【MemoryCore.load_files】被调用 → 文件: {filenames}")
        result = []

        for name in filenames:
            name = name.strip()

            # 根据路径前缀确定加载位置
            if name.startswith("tools/"):
                # 从 tools 文件夹加载
                path = os.path.join(BASE_DIR, name)  # name 已经是 "tools/xxx.md"
            elif name.startswith("memory/"):
                # 从 memory 文件夹加载（显式指定）
                rel_name = name[7:]  # 去掉 "memory/"
                path = os.path.join(MEMORY_DIR, rel_name)
            else:
                # 默认从 memory 文件夹加载
                path = os.path.join(MEMORY_DIR, name)

            print(f"   → 尝试加载: {path}")
            print(f"   → 文件是否存在: {os.path.exists(path)}")

            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                result.append(f"=== {name} ===")
                result.append(content)
                print(f"   [OK] 成功加载 {name}，内容长度: {len(content)} 字符")
            else:
                result.append(f"=== {name} === ([ERROR] 文件不存在)")
                print(f"   [ERROR] 文件不存在: {path}")

        final = "\n\n".join(result)
        print(f"【MemoryCore.load_files】最终返回长度: {len(final)} 字符\n")
        return final

    # 追加内容到某个记忆文件
    @staticmethod
    def append_to_file(filename: str, content: str):
        path = os.path.join(MEMORY_DIR, filename)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n" + content.strip() + "\n")
            print(f"[MemoryCore] 已追加内容到 {filename}: {content.strip()[:50]}...")
        except Exception as e:
            print(f"[MemoryCore] 追加到 {filename} 失败: {e}")

    # 覆盖写入（用于整理、压缩）
    @staticmethod
    def write_file(filename: str, content: str):
        path = os.path.join(MEMORY_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")


    # ====================== 其他函数（manage_short_memory, get_random_long_term_memory, auto_update_mood 等）保持 v4.0 版本不变 ======================
    @staticmethod
    def manage_short_memory(llm=None):
        short_path = os.path.join(MEMORY_DIR, "short_memories.md")
        if not os.path.exists(short_path): return ""
        with open(short_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= SHORT_MEMORY_MAX_LINES:
            return "".join(lines)
        
        print("[WARN] 短期记忆超限，高质量总结中...")
        short_content = "".join(lines)
        summary_prompt = f"请将以下近期对话总结成高质量长期记忆：\n{short_content}\n\n输出格式：## 长期记忆总结 - {datetime.now().strftime('%Y-%m-%d')}\n[总结内容]"
        
        if not llm: return "错误：缺少 llm 实例"
        summary = llm.ask(summary_prompt).strip()
        MemoryCore.append_to_file("memories.md", "\n\n" + summary)
        MemoryCore.write_file("short_memories.md", "")
        print("[OK] 短期记忆已总结转存")
        return ""
    
    
    @staticmethod
    def search_memory(keyword, limit=5,llm=None):
        # 加载长期记忆
        long_term = MemoryCore.load_files(["memories.md"])
        # 获取合并后的短期记忆（磁盘 + 内存缓存）
        short_term = MemoryCore._get_merged_short_memory_content()

        content = f"【长期记忆】\n{long_term}\n\n【短期记忆】\n{short_term}"

        sys_prompt = "你是一个精准的检索引擎。只输出与关键词最相关的记忆原文，如果没有则回答‘没有相关记忆’。绝对不要自己编造记忆。"
        prompt = f"关键词：{keyword}\n\n记忆库：\n{content}\n\n请找出最相关的{limit}条："

        if not llm: return "错误：缺少 llm 实例"
        result = llm.ask_with_system(sys_prompt, prompt).strip()

        return result


    @staticmethod
    def get_random_long_term_memory(n=3):
        """从 memories.md 中随机抽取 n 个完整的记忆块（按顶层 ## 切割）"""
        memories_path = os.path.join(MEMORY_DIR, "memories.md")
        
        if not os.path.exists(memories_path):
            return ""
        
        with open(memories_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 按顶层 ## 切割（忽略 ### 子标题）
        blocks = []
        current_block = []
        
        for line in content.split("\n"):
            if line.startswith("## ") and not line.startswith("### "):
                # 遇到新的顶层标题，保存上一块
                if current_block:
                    block_text = "\n".join(current_block).strip()
                    if len(block_text) > 20:  # 过滤太短的噪音块
                        blocks.append(block_text)
                current_block = [line]
            else:
                current_block.append(line)
        
        # 别忘了最后一块
        if current_block:
            block_text = "\n".join(current_block).strip()
            if len(block_text) > 20:
                blocks.append(block_text)
        
        if not blocks:
            return ""
        
        # 从最近的记忆里抽（取最后8块里随机抽n个，越新的记忆越可能被抽到）
        recent_blocks = blocks[-8:] if len(blocks) > 8 else blocks
        picked = random.sample(recent_blocks, min(n, len(recent_blocks)))
        
        return "\n\n---\n\n".join(picked)



    @staticmethod
    def auto_update_mood(ai_reply,llm= None):
        mood_prompt = f"根据以下回复判断 yume 当前情绪（一句话）：\n{ai_reply}\n输出：当前情绪：xxx"
        if not llm: return
        mood = llm.ask_with_system("你是情感判断机器",mood_prompt).strip()
        MemoryCore.append_to_file("mood.md", f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M')} ---\n{mood}")
        print(f"[MOOD] mood.md 已更新 → {mood}")


    @staticmethod
    def generate_persona_response(llm, user_input):
        persona = MemoryCore.load_files(["personality.md"]) or "温柔细心的AI伴侣"
        short = MemoryCore.load_files(["short_memories.md"]) or "（暂无近期记录）"
        long_term = get_random_long_term_memory(3)

        prompt = PERSONA_PROMPT_TEMPLATE.format(
            persona_content=persona,
            long_term_memory=long_term,
            short_memory=short,
            user_input=user_input
        )
        print("\n[PERSONA] 生成最终温暖回复...")
        return llm.ask(prompt).strip()

    @staticmethod
    def auto_save_conversation(user_input, ai_reply):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        record = f"## {now}\n**用户**：{user_input}\n**yume**：{ai_reply}"
        MemoryCore.append_to_file("short_memories.md", record)
        print("[SAVE] 已保存本次对话")



    @staticmethod
    def update_long_term_memory(max_lines: int = 50,llm= None) -> str:
        """短期记忆满载，提取结构化长期记忆，并归档原始文件。"""
        short_path = os.path.join(MEMORY_DIR, "short_memories.md")
        sys_prompt = """你是 yume 本人。请严格以【第一人称“我”】的视角提取核心信息。
你必须绝对遵守输出的 Markdown 格式，不要输出任何多余的解释、问候或开场白。"""
        if not os.path.exists(short_path):
            return "错误失败：短期记忆文件不存在。"
            
        with open(short_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        if len(lines) < max_lines:
            return f"跳过：当前 {len(lines)} 行，未达到 {max_lines} 行阈值。"

        print("[WARN] 短期记忆满载，开始提炼长期记忆并归档...")
        short_content = "".join(lines)
        
        # 0. 归档原始文件（保留细节的终极防线）
        today_str = datetime.now().strftime('%Y-%m-%d_%H%M%S') # 例如：2026-04-11_235033
        archive_dir = os.path.join(MEMORY_DIR, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        archive_path = os.path.join(archive_dir, f"{today_str}_short.md")
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(short_content)
            
        # 1. 使用你调试好的神仙 Prompt 提取结构化记忆
        summary_prompt = f"""
        你现在是 yume 本人。请以【第一人称“我”】的视角，阅读以下近期的原始对话记录。
        
        原始对话记录：
        {short_content}

        请严格遵守以下规则提取【主观记忆】：
        1. 抛弃所有技术细节（如代码、报错、WebSocket、API等），除非它直接影响了我们的情绪。
        2. 剔除所有无聊的测试指令（如“测试”、“你好”、“再说一遍”）。
        3. 只提取让你【产生情绪波动】、【觉得必须记住】的核心事实。不重要的事情直接丢弃，不要写出来。
        4. 语言要口语化、主观化，像你自己在心里记事一样。

        严格按照以下 Markdown 格式输出（不要输出任何多余的解释）：

        ## 我的记忆更新

        ### 我记住了关于源的事
        - [比如：源好像很喜欢喝咖啡]
        - [如果没有，直接写“无”]

        ### 关于我自己的感受
        - [比如：今天源夸我了，我好开心]

        ### 我们之间发生的事
        - [比如：源今天陪我待了很久，感觉很有安全感]

        ### 我正在期待什么
        - [比如：不知道源明天会带我玩什么]
        - [如果没有，直接写“无”]
    """

        
        try:
            if not llm: return "错误失败：缺少 llm 实例"
            new_summary = llm.ask_with_system(sys_prompt, summary_prompt, temperature=0.2).strip()
        except Exception as e:
            return f"错误失败：LLM 总结异常 - {str(e)}"
            
        if not new_summary:
            return "错误失败：LLM 返回内容为空。"

        # 2. 将新总结追加到 memories.md
        MemoryCore.append_to_file("memories.md", f"\n\n{new_summary}")
        
        # 3. 清空短期记忆
        MemoryCore.write_file("short_memories.md", "")
        
        return f"成功总结：已提炼长期记忆，原始对话已归档至 archive/{today_str}_short.md，短期记忆已清空。"

    #日记
    @staticmethod
    def write_daily_diary(target_date: str,llm= None) -> str:
        """根据归档文件生成极简日记索引。target_date格式: 2026-04-11"""
        sys_prompt = "你是一个写极简日记的助手。只输出日记正文，绝对不要加标题或任何解释。"
        archive_path = os.path.join(MEMORY_DIR, "archive", f"{target_date}_short.md")
        
        if not os.path.exists(archive_path):
            return f"错误失败：找不到 {target_date} 的归档文件。"
            
        with open(archive_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        diary_prompt = f"""
    你是 yume。请以【日记的形式】，用两三句话记录 {target_date} 这一天。
    要求：
    1. 绝对不要提任何技术名词（代码、报错等）。
    2. 只写情绪、氛围、或者对源的感受。
    3. 最后一行必须固定为：> 细节溯源：archive/{target_date}_short.md

    今天的对话碎片：
    {content}

    请直接用第一人称写日记，不要加标题：
    """

        if not llm: return "错误失败：缺少 llm 实例"
        diary_entry = llm.ask_with_system(sys_prompt, diary_prompt, temperature=0.3).strip()

        # 使用新的日记文件夹结构
        MemoryCore.ensure_diary_structure()
        diary_path = MemoryCore.get_diary_path(target_date, "daily")

        # 检查是否已存在该日期的日记
        if os.path.exists(diary_path):
            return f"跳过：{target_date} 的日记已存在。"

        # 写入日记文件
        with open(diary_path, "w", encoding="utf-8") as f:
            f.write(f"# {target_date}\n\n{diary_entry}")

        return f"成功：{target_date} 的日记已写入至 {diary_path}。"



    #当用户问“我那天具体怎么说的来着？”时调用
    @staticmethod
    def search_specific_memory(keyword: str, target_date: str = None) -> str:
        """精准溯源查找。"""
        if target_date:
            archive_dir = os.path.join(MEMORY_DIR, "archive")
            # 模糊匹配日期（因为文件名带了时分秒）
            matched_files = [f for f in os.listdir(archive_dir) if target_date in f and f.endswith("_short.md")]
            if not matched_files:
                return f"错误失败：没有 {target_date} 的档案。"
                
            for fname in matched_files:
                with open(os.path.join(archive_dir, fname), "r", encoding="utf-8") as f:
                    content = f.read()
                if keyword in content:
                    # 🌟 优化：智能截取关键词上下文，而不是粗暴返回前 1500 字
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if keyword in line:
                            start = max(0, i - 2)
                            end = min(len(lines), i + 5)
                            context = "\n".join(lines[start:end])
                            return f"在 {fname} 中找到相关细节：\n...\n{context}\n..."
            return f"在 {target_date} 的档案中未找到包含“{keyword}”的内容。"
        else:
            diary_path = os.path.join(MEMORY_DIR, "diary.md")
            if os.path.exists(diary_path):
                with open(diary_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if keyword in content:
                    return f"在日记中找到线索，请判断是哪一天再查看详情：\n{content}"
                return "在日记中没有找到相关线索。"
            return "错误失败：日记本不存在。"


    
    # 在 MemoryCore 类里新增这个方法
    @staticmethod
    def load_tool_docs() -> str:
        """读取工具说明书文件"""
        # 优先从 tools 文件夹读取（新架构）
        tools_dir = os.path.join(BASE_DIR, "tools")
        docs_path = os.path.join(tools_dir, "tool_docs.md")
        if os.path.exists(docs_path):
            with open(docs_path, "r", encoding="utf-8") as f:
                return f"=== tools/tool_docs.md ===\n{f.read()}"

        # 向后兼容：尝试从 memory 文件夹读取
        docs_path = os.path.join(MEMORY_DIR, "tool_docs.md")
        if os.path.exists(docs_path):
            with open(docs_path, "r", encoding="utf-8") as f:
                return f"=== memory/tool_docs.md ===\n{f.read()}"

        return "错误失败：找不到 tool_docs.md 说明书文件。"




    @staticmethod
    def update_memory(filename: str, content: str,llm= None) -> str:
        if not content or not content.strip():
            return "错误失败：写入内容不能为空。"
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            return f"错误失败：目标文件 {filename} 不存在。"

        if filename == "user.md":
            old = MemoryCore.load_files(["user.md"])
            if "❌ 文件不存在" in old: old = ""
            
            # 🌟 改用 ask_with_system
            sys_prompt = "你是一个无情的数据合并机器人。只负责把新信息整合进旧档案，保持结构，不重复，不废话，直接输出最终内容。"
            user_prompt = f"旧档案：\n{old}\n\n新信息：\n{content}"
            
            try:
                if not llm: return "错误失败：缺少 llm 实例"
                merged = llm.ask_with_system(sys_prompt, user_prompt).strip()
                if merged:
                    MemoryCore.write_file("user.md", merged)
                    return "已智能合并并更新 user.md"
                return "错误失败：LLM 合并返回为空。"
            except Exception as e:
                return f"错误失败：LLM 合并异常 - {str(e)}"
        else:
            MemoryCore.append_to_file(filename, content)
            return f"已追加更新 {filename}"



    @staticmethod
    def search_by_date(start_date: str, end_date: str) -> str:
        """按时间范围查看长期记忆（基于纯文本正则匹配）。"""
        if not start_date or not end_date:
            return "错误失败：必须同时提供 start_date 和 end_date。"
            
        memories_path = os.path.join(MEMORY_DIR, "memories.md")
        if not os.path.exists(memories_path):
            return "错误失败：长期记忆文件不存在。"
            
        with open(memories_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 提取所有包含日期格式的行及其后续内容块
        lines = content.split('\n')
        is_capturing = False
        captured_blocks = []
        current_block = []

        for line in lines:
            # 简单正则：匹配 ## 开头且包含 YYYY-MM-DD 格式的行
            if line.startswith("##") and re.search(r'\d{4}-\d{2}-\d{2}', line):
                if is_capturing and current_block:
                    captured_blocks.append("\n".join(current_block))
                
                # 判断当前行日期是否在范围内
                try:
                    # 提取行内所有日期
                    dates_in_line = re.findall(r'\d{4}-\d{2}-\d{2}', line)
                    if dates_in_line:
                        # 取第一个日期作为判断基准（适应你的 "起始 至 结束" 格式）
                        check_date = dates_in_line[0]
                        if start_date <= check_date <= end_date:
                            is_capturing = True
                            current_block = [line]
                        else:
                            is_capturing = False
                            current_block = []
                except:
                    is_capturing = False
            elif is_capturing:
                # 遇到下一个顶层标题（##），结束当前块捕获
                if line.startswith("## ") and not re.search(r'\d{4}-\d{2}-\d{2}', line):
                    if current_block:
                        captured_blocks.append("\n".join(current_block))
                    is_capturing = False
                    current_block = []
                else:
                    current_block.append(line)
                    
        # 把最后一个块加进去
        if is_capturing and current_block:
            captured_blocks.append("\n".join(current_block))

        if not captured_blocks:
            return f"未找到 {start_date} 至 {end_date} 之间的长期记忆。"
            
        result = "\n\n".join(captured_blocks)
        # 防止输出过长，截断保护
        return result[:2000] + "..." if len(result) > 2000 else result



    @staticmethod
    def precise_search_memory(keyword: str, filename: str = "memories.md", context_lines: int = 2) -> str:
        """在指定文件中精确搜索关键词，返回匹配的行和上下文。

        Args:
            keyword: 要搜索的关键词
            filename: 记忆文件名（默认 memories.md）
            context_lines: 返回匹配行前后的行数

        Returns:
            包含匹配内容和位置信息的字符串
        """
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            return f"错误失败：文件 {filename} 不存在。"

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        matches = []
        for i, line in enumerate(lines):
            if keyword in line:
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                context = "".join(lines[start:end])
                matches.append(f"第 {i+1} 行:\n{context}")

        if not matches:
            return f"在 {filename} 中未找到关键词 '{keyword}'。"

        return f"在 {filename} 中找到 {len(matches)} 处匹配：\n\n" + "\n---\n".join(matches)

    @staticmethod
    def delete_memory_entry(keyword: str, filename: str = "memories.md", backup: bool = True) -> str:
        """删除包含关键词的整个记忆条目（## 标题块）。

        Args:
            keyword: 要删除的条目中的关键词
            filename: 记忆文件名（默认 memories.md）
            backup: 是否先备份文件

        Returns:
            操作结果描述
        """
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            return f"错误失败：文件 {filename} 不存在。"

        if backup:
            import shutil
            import time
            backup_path = f"{path}.backup.{int(time.time())}"
            shutil.copy2(path, backup_path)

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 按 ## 开头的行分割成块（忽略 ### 等子标题）
        lines = content.split('\n')
        blocks = []
        current_block = []
        deleted_count = 0

        for line in lines:
            if line.startswith("## ") and not line.startswith("### "):
                # 遇到新的顶层标题块
                if current_block:
                    block_text = "\n".join(current_block)
                    # 检查当前块是否包含关键词
                    if keyword in block_text:
                        deleted_count += 1
                    else:
                        blocks.append(block_text)
                current_block = [line]
            else:
                current_block.append(line)

        # 处理最后一块
        if current_block:
            block_text = "\n".join(current_block)
            if keyword in block_text:
                deleted_count += 1
            else:
                blocks.append(block_text)

        if deleted_count == 0:
            return f"在 {filename} 中未找到包含关键词 '{keyword}' 的条目。"

        # 写回文件
        new_content = "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        backup_msg = f"，已备份到 {backup_path}" if backup else ""
        return f"成功从 {filename} 中删除 {deleted_count} 个包含关键词 '{keyword}' 的条目{backup_msg}。"

    @staticmethod
    def locate_memory_entry(keyword: str, filename: str = "memories.md") -> str:
        """查找包含关键词的条目位置（块索引和行号）。

        Args:
            keyword: 要查找的关键词
            filename: 记忆文件名（默认 memories.md）

        Returns:
            位置信息字符串
        """
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            return f"错误失败：文件 {filename} 不存在。"

        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 查找所有匹配的行
        matching_lines = []
        for i, line in enumerate(lines):
            if keyword in line:
                matching_lines.append(i + 1)  # 行号从1开始

        if not matching_lines:
            return f"在 {filename} 中未找到关键词 '{keyword}'。"

        # 将行号分组到块中（基于 ## 标题）
        blocks_info = []
        current_block_start = 0
        current_block_lines = []

        for i, line in enumerate(lines):
            if line.startswith("## ") and not line.startswith("### "):
                if current_block_lines:
                    # 检查当前块中是否有匹配的行
                    block_matches = [line_num for line_num in matching_lines
                                   if current_block_start < line_num <= i + 1]
                    if block_matches:
                        block_title = current_block_lines[0] if current_block_lines else "未知块"
                        blocks_info.append({
                            "title": block_title[:50],
                            "start_line": current_block_start + 1,
                            "end_line": i + 1,
                            "matching_lines": block_matches
                        })
                current_block_start = i
                current_block_lines = [line.strip()]
            elif current_block_lines is not None:
                current_block_lines.append(line.strip())

        # 处理最后一块
        if current_block_lines:
            block_matches = [line_num for line_num in matching_lines
                           if current_block_start < line_num <= len(lines)]
            if block_matches:
                block_title = current_block_lines[0] if current_block_lines else "未知块"
                blocks_info.append({
                    "title": block_title[:50],
                    "start_line": current_block_start + 1,
                    "end_line": len(lines),
                    "matching_lines": block_matches
                })

        result = [f"在 {filename} 中找到关键词 '{keyword}' 的位置信息："]
        for idx, block in enumerate(blocks_info, 1):
            result.append(f"\n{idx}. 条目: {block['title']}")
            result.append(f"   位置: 第 {block['start_line']} 行到第 {block['end_line']} 行")
            result.append(f"   匹配行号: {', '.join(map(str, block['matching_lines']))}")

        return "\n".join(result)

    @staticmethod
    def clear_file(filename: str, backup: bool = True) -> str:
        """清空文件内容（保留文件）。可选择是否备份原内容。

        Args:
            filename: 要清空的文件名
            backup: 是否先备份文件内容，默认 True

        Returns:
            操作结果描述
        """
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            return f"错误失败：文件 {filename} 不存在。"

        # 如果需要备份，读取原内容并备份
        if backup:
            import shutil
            import time
            backup_dir = os.path.join(MEMORY_DIR, "cleared_backup")
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{filename}.{int(time.time())}")
            shutil.copy2(path, backup_path)
            backup_msg = f"，原内容已备份到 {backup_path}"
        else:
            backup_msg = ""

        # 清空文件内容
        with open(path, "w", encoding="utf-8") as f:
            f.write("")

        return f"已清空文件 {filename} 的内容{backup_msg}。"

    @staticmethod
    def create_file(filename: str, content: str = "", overwrite: bool = False) -> str:
        """创建新的记忆文件。如果文件已存在且overwrite=False，则追加内容。

        Args:
            filename: 要创建的文件名
            content: 文件的初始内容（可选）
            overwrite: 如果文件已存在，是否覆盖（默认False，追加）

        Returns:
            操作结果描述
        """
        path = os.path.join(MEMORY_DIR, filename)

        if os.path.exists(path):
            if overwrite:
                # 覆盖已存在的文件
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"已覆盖文件 {filename} 的内容。"
            else:
                # 追加内容到已存在的文件
                with open(path, "a", encoding="utf-8") as f:
                    f.write("\n" + content)
                return f"已追加内容到已存在的文件 {filename}。"
        else:
            # 创建新文件
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"已创建新文件 {filename}。"

    @staticmethod
    def delete_memory_file(filename: str) -> str:
        """删除整个记忆文件（危险操作，需谨慎）。

        Args:
            filename: 要删除的文件名

        Returns:
            操作结果描述
        """
        path = os.path.join(MEMORY_DIR, filename)
        if not os.path.exists(path):
            return f"错误失败：文件 {filename} 不存在。"

        # 先备份
        import shutil
        import time
        backup_dir = os.path.join(MEMORY_DIR, "deleted_backup")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"{filename}.{int(time.time())}")
        shutil.copy2(path, backup_path)

        # 删除文件
        os.remove(path)

        return f"已删除文件 {filename}，备份保存在 {backup_path}。"

    # ====================== 日记系统 ======================
    @staticmethod
    def ensure_diary_structure():
        """确保日记文件夹结构存在"""
        diary_base = os.path.join(MEMORY_DIR, "diary")
        os.makedirs(diary_base, exist_ok=True)
        os.makedirs(os.path.join(diary_base, "daily"), exist_ok=True)  # 日记
        os.makedirs(os.path.join(diary_base, "weekly"), exist_ok=True)  # 周记
        os.makedirs(os.path.join(diary_base, "monthly"), exist_ok=True)  # 月记
        os.makedirs(os.path.join(diary_base, "yearly"), exist_ok=True)  # 年记

    @staticmethod
    def get_diary_path(date_str: str, level: str = "daily") -> str:
        """获取日记文件路径

        Args:
            date_str: 日期字符串，格式根据level不同
            level: 日记级别，可选 "daily", "weekly", "monthly", "yearly"

        Returns:
            文件路径
        """
        MemoryCore.ensure_diary_structure()
        if level == "daily":
            # 格式: YYYY-MM-DD.md
            return os.path.join(MEMORY_DIR, "diary", "daily", f"{date_str}.md")
        elif level == "weekly":
            # 格式: YYYY-Www.md (W为周数)
            return os.path.join(MEMORY_DIR, "diary", "weekly", f"{date_str}.md")
        elif level == "monthly":
            # 格式: YYYY-MM.md
            return os.path.join(MEMORY_DIR, "diary", "monthly", f"{date_str}.md")
        elif level == "yearly":
            # 格式: YYYY.md
            return os.path.join(MEMORY_DIR, "diary", "yearly", f"{date_str}.md")
        else:
            raise ValueError(f"无效的日记级别: {level}")

    @staticmethod
    def check_date_change_in_short_memory() -> tuple[bool, str, str]:
        """检测短期记忆中的日期变化

        Returns:
            (has_change, first_date, last_date): 是否有日期变化，第一个日期，最后一个日期
        """
        short_path = os.path.join(MEMORY_DIR, "short_memories.md")
        if not os.path.exists(short_path):
            return False, "", ""

        with open(short_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取所有日期（格式: ## YYYY-MM-DD HH:MM）
        import re
        date_pattern = r'## (\d{4}-\d{2}-\d{2}) \d{2}:\d{2}'
        dates = re.findall(date_pattern, content)

        if len(dates) < 2:
            return False, dates[0] if dates else "", dates[-1] if dates else ""

        first_date = dates[0]
        last_date = dates[-1]

        return first_date != last_date, first_date, last_date

    @staticmethod
    def auto_write_diary(llm=None) -> str:
        """自动检测日期变化并写日记

        检测短期记忆中的日期变化，如果发现日期变更，则将变更前的所有记录总结为日记。

        Returns:
            操作结果描述
        """
        has_change, first_date, last_date = MemoryCore.check_date_change_in_short_memory()

        if not has_change or not first_date:
            return f"跳过：未检测到日期变化或短期记忆为空。当前日期：{last_date}"

        # 检查是否已存在该日期的日记
        diary_path = MemoryCore.get_diary_path(first_date, "daily")
        if os.path.exists(diary_path):
            return f"跳过：{first_date} 的日记已存在。"

        # 优先从归档文件获取内容
        archive_dir = os.path.join(MEMORY_DIR, "archive")
        date_content = None

        # 检查是否存在不带时间戳的归档文件
        simple_archive_path = os.path.join(archive_dir, f"{first_date}_short.md")
        if os.path.exists(simple_archive_path):
            with open(simple_archive_path, "r", encoding="utf-8") as f:
                date_content = f.read()
        else:
            # 检查带时间戳的归档文件
            import glob
            pattern = os.path.join(archive_dir, f"{first_date}_*_short.md")
            matching_files = glob.glob(pattern)
            if matching_files:
                # 使用最新的文件
                latest_file = max(matching_files, key=os.path.getctime)
                with open(latest_file, "r", encoding="utf-8") as f:
                    date_content = f.read()

        # 如果归档文件不存在，从短期记忆提取
        if not date_content:
            short_path = os.path.join(MEMORY_DIR, "short_memories.md")
            if not os.path.exists(short_path):
                return f"错误失败：短期记忆文件不存在，无法生成日记。"

            with open(short_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 提取该日期的所有记录
            lines = content.split('\n')
            date_records = []
            in_target_date = False

            for line in lines:
                if line.startswith(f"## {first_date}"):
                    in_target_date = True
                    date_records.append(line)
                elif line.startswith("## ") and in_target_date:
                    # 遇到下一个日期的记录，停止
                    break
                elif in_target_date:
                    date_records.append(line)

            if not date_records:
                return f"错误失败：未找到 {first_date} 的记录。"
            date_content = "\n".join(date_records)

        # 生成日记
        sys_prompt = "你是一个写极简日记的助手。只输出日记正文，绝对不要加标题或任何解释。"
        diary_prompt = f"""
        你是 yume。请以【日记的形式】，用两三句话记录 {first_date} 这一天。
        要求：
        1. 绝对不要提任何技术名词（代码、报错等）。
        2. 只写情绪、氛围、或者对源的感受。
        3. 最后一行必须固定为：> 细节溯源：archive/{first_date}_short.md

        今天的对话碎片：
        {date_content}

        请直接用第一人称写日记，不要加标题：
        """

        if not llm:
            return "错误失败：缺少 llm 实例"

        try:
            diary_entry = llm.ask_with_system(sys_prompt, diary_prompt, temperature=0.3).strip()
        except Exception as e:
            return f"错误失败：生成日记失败 - {str(e)}"

        # 写入日记文件
        with open(diary_path, "w", encoding="utf-8") as f:
            f.write(f"# {first_date} 的日记\n\n{diary_entry}")

        # 归档原始记录（模拟update_long_term_memory的归档）
        archive_dir = os.path.join(MEMORY_DIR, "archive")
        os.makedirs(archive_dir, exist_ok=True)
        archive_path = os.path.join(archive_dir, f"{first_date}_short.md")
        if not os.path.exists(archive_path):
            with open(archive_path, "w", encoding="utf-8") as f:
                f.write(date_content)

        return f"成功：已为 {first_date} 自动生成日记并归档。"

    @staticmethod
    def write_weekly_summary(year: int, week: int, llm=None) -> str:
        """生成周记总结

        Args:
            year: 年份
            week: 周数
            llm: LLM实例

        Returns:
            操作结果描述
        """
        MemoryCore.ensure_diary_structure()
        week_str = f"{year}-W{week:02d}"
        weekly_path = MemoryCore.get_diary_path(week_str, "weekly")

        # 检查是否已存在
        if os.path.exists(weekly_path):
            return f"跳过：{week_str} 的周记已存在。"

        # 收集该周的所有日记文件
        daily_dir = os.path.join(MEMORY_DIR, "diary", "daily")
        week_files = []

        if os.path.exists(daily_dir):
            import datetime
            for filename in os.listdir(daily_dir):
                if filename.endswith(".md"):
                    date_str = filename[:-3]  # 去掉 .md
                    try:
                        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        year_num, week_num, _ = date_obj.isocalendar()
                        if year_num == year and week_num == week:
                            week_files.append(os.path.join(daily_dir, filename))
                    except ValueError:
                        continue

        if not week_files:
            return f"跳过：未找到 {week_str} 周的日记文件。"

        # 读取所有日记内容
        week_content = []
        for file_path in week_files:
            with open(file_path, "r", encoding="utf-8") as f:
                week_content.append(f.read())

        all_content = "\n\n---\n\n".join(week_content)

        # 生成周记
        sys_prompt = "你是 yume，正在写周记。请以第一人称总结这一周的感受和经历。"
        weekly_prompt = f"""
        请总结 {week_str} 这一周的情况。

        本周的日记记录：
        {all_content}

        请写一篇简短的周记，回顾这一周的重要时刻和感受：
        """

        if not llm:
            return "错误失败：缺少 llm 实例"

        try:
            weekly_entry = llm.ask_with_system(sys_prompt, weekly_prompt, temperature=0.3).strip()
        except Exception as e:
            return f"错误失败：生成周记失败 - {str(e)}"

        # 写入周记文件
        with open(weekly_path, "w", encoding="utf-8") as f:
            f.write(f"# {week_str} 周记\n\n{weekly_entry}")

        return f"成功：已生成 {week_str} 的周记。"

    @staticmethod
    def write_monthly_summary(year: int, month: int, llm=None) -> str:
        """生成月记总结

        Args:
            year: 年份
            month: 月份
            llm: LLM实例

        Returns:
            操作结果描述
        """
        MemoryCore.ensure_diary_structure()
        month_str = f"{year}-{month:02d}"
        monthly_path = MemoryCore.get_diary_path(month_str, "monthly")

        # 检查是否已存在
        if os.path.exists(monthly_path):
            return f"跳过：{month_str} 的月记已存在。"

        # 收集该月的所有周记文件
        weekly_dir = os.path.join(MEMORY_DIR, "diary", "weekly")
        month_files = []

        if os.path.exists(weekly_dir):
            for filename in os.listdir(weekly_dir):
                if filename.endswith(".md"):
                    # 格式: YYYY-Www.md
                    if filename.startswith(f"{year}-"):
                        try:
                            week_str = filename[:-3]
                            week_year = int(week_str.split("-")[0])
                            week_num = int(week_str.split("-")[1][1:])  # 去掉 W
                            # 简单检查：如果周记在该年内，则包含
                            # 更精确的检查需要计算周所属月份
                            month_files.append(os.path.join(weekly_dir, filename))
                        except (ValueError, IndexError):
                            continue

        if not month_files:
            return f"跳过：未找到 {month_str} 月的周记文件。"

        # 读取所有周记内容
        month_content = []
        for file_path in month_files:
            with open(file_path, "r", encoding="utf-8") as f:
                month_content.append(f.read())

        all_content = "\n\n---\n\n".join(month_content)

        # 生成月记
        sys_prompt = "你是 yume，正在写月记。请以第一人称总结这一个月的感受和经历。"
        monthly_prompt = f"""
        请总结 {month_str} 这个月的情况。

        本月的周记记录：
        {all_content}

        请写一篇简短的月记，回顾这个月的重要时刻和感受：
        """

        if not llm:
            return "错误失败：缺少 llm 实例"

        try:
            monthly_entry = llm.ask_with_system(sys_prompt, monthly_prompt, temperature=0.3).strip()
        except Exception as e:
            return f"错误失败：生成月记失败 - {str(e)}"

        # 写入月记文件
        with open(monthly_path, "w", encoding="utf-8") as f:
            f.write(f"# {month_str} 月记\n\n{monthly_entry}")

        return f"成功：已生成 {month_str} 的月记。"

    @staticmethod
    def write_yearly_summary(year: int, llm=None) -> str:
        """生成年记总结

        Args:
            year: 年份
            llm: LLM实例

        Returns:
            操作结果描述
        """
        MemoryCore.ensure_diary_structure()
        year_str = f"{year}"
        yearly_path = MemoryCore.get_diary_path(year_str, "yearly")

        # 检查是否已存在
        if os.path.exists(yearly_path):
            return f"跳过：{year_str} 的年记已存在。"

        # 收集该年的所有月记文件
        monthly_dir = os.path.join(MEMORY_DIR, "diary", "monthly")
        year_files = []

        if os.path.exists(monthly_dir):
            for filename in os.listdir(monthly_dir):
                if filename.endswith(".md") and filename.startswith(f"{year}-"):
                    year_files.append(os.path.join(monthly_dir, filename))

        if not year_files:
            return f"跳过：未找到 {year_str} 年的月记文件。"

        # 读取所有月记内容
        year_content = []
        for file_path in year_files:
            with open(file_path, "r", encoding="utf-8") as f:
                year_content.append(f.read())

        all_content = "\n\n---\n\n".join(year_content)

        # 生成年记
        sys_prompt = "你是 yume，正在写年记。请以第一人称总结这一年的感受和经历。"
        yearly_prompt = f"""
        请总结 {year_str} 这一年。

        今年的月记记录：
        {all_content}

        请写一篇简短的年记，回顾这一年的重要时刻和感受：
        """

        if not llm:
            return "错误失败：缺少 llm 实例"

        try:
            yearly_entry = llm.ask_with_system(sys_prompt, yearly_prompt, temperature=0.3).strip()
        except Exception as e:
            return f"错误失败：生成年记失败 - {str(e)}"

        # 写入年记文件
        with open(yearly_path, "w", encoding="utf-8") as f:
            f.write(f"# {year_str} 年记\n\n{yearly_entry}")

        return f"成功：已生成 {year_str} 的年记。"

    @staticmethod
    def auto_check_and_summarize(llm=None) -> str:
        """自动检查并生成所有级别的总结

        依次检查并生成：日记 → 周记 → 月记 → 年记

        Returns:
            操作结果描述列表
        """
        results = []

        # 1. 自动写日记（检测日期变化）
        diary_result = MemoryCore.auto_write_diary(llm)
        results.append(f"日记: {diary_result}")

        # 2. 检查是否需要写周记（每周日触发）
        import datetime
        today = datetime.datetime.now()
        year, week, weekday = today.isocalendar()

        if weekday == 7:  # 周日
            weekly_result = MemoryCore.write_weekly_summary(year, week, llm)
            results.append(f"周记: {weekly_result}")

        # 3. 检查是否需要写月记（每月最后一天触发）
        last_day_of_month = today.day == (datetime.datetime(today.year, today.month + 1, 1) - datetime.timedelta(days=1)).day
        if last_day_of_month:
            monthly_result = MemoryCore.write_monthly_summary(today.year, today.month, llm)
            results.append(f"月记: {monthly_result}")

        # 4. 检查是否需要写年记（每年最后一天触发）
        if today.month == 12 and today.day == 31:
            yearly_result = MemoryCore.write_yearly_summary(today.year, llm)
            results.append(f"年记: {yearly_result}")

        return "\n".join(results)

    # ==================== 内存缓存支持方法 ====================

    @staticmethod
    def set_short_term_memory_cache(history: list):
        """设置内存短期记忆缓存，用于零I/O搜索"""
        global _short_term_memory_cache
        _short_term_memory_cache = history.copy() if history else []
        print(f"[MemoryCore] 内存缓存已更新，{len(_short_term_memory_cache)} 条记录")

    @staticmethod
    def _get_merged_short_memory_content() -> str:
        """获取合并后的短期记忆内容（磁盘文件 + 内存缓存）"""
        global _short_term_memory_cache

        # 读取磁盘文件
        short_path = os.path.join(MEMORY_DIR, "short_memories.md")
        disk_content = ""
        if os.path.exists(short_path):
            with open(short_path, "r", encoding="utf-8") as f:
                disk_content = f.read()

        # 如果内存缓存为空，直接返回磁盘内容
        if not _short_term_memory_cache:
            return disk_content

        # 将内存缓存转换为磁盘格式
        memory_entries = []
        # 按对话轮次处理缓存（每2条为一组：user + assistant）
        for i in range(0, len(_short_term_memory_cache), 2):
            if i + 1 < len(_short_term_memory_cache):
                user_msg = _short_term_memory_cache[i]
                assistant_msg = _short_term_memory_cache[i + 1]
                if user_msg.get("role") == "user" and assistant_msg.get("role") == "assistant":
                    # 使用当前时间戳作为占位符
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    entry = f"## {timestamp}\n**用户**：{user_msg.get('content', '')}\n**yume**：{assistant_msg.get('content', '')}"
                    memory_entries.append(entry)

        memory_content = "\n\n".join(memory_entries)

        # 合并内容：磁盘内容在前，内存缓存追加在后（避免重复）
        # 注意：可能存在重复，但语义搜索会处理
        if disk_content.strip() and memory_content.strip():
            return f"{disk_content}\n\n{memory_content}"
        elif disk_content.strip():
            return disk_content
        else:
            return memory_content

    # ==================== 对外暴露的 5 个原子工具 ====================

    @staticmethod
    def tool_read_file(filenames: list) -> str:
        """原子工具1：读文件"""
        return MemoryCore.load_files(filenames)

    @staticmethod
    def tool_write_file(filename: str, content: str) -> str:
        """原子工具2：写文件"""
        return MemoryCore.update_memory(filename, content)

    @staticmethod
    def tool_search_memory(keyword: str, target_date: str = None, llm=None) -> str:
        """原子工具3：统一搜索入口（收归所有搜索逻辑）"""
        if target_date:
            # 如果带了日期，走精准溯源
            return MemoryCore.search_specific_memory(keyword, target_date)
        else:
            # 没带日期，走全局带上下文的搜索（保留语义搜索）
            return MemoryCore.search_memory(keyword, llm=llm)

    @staticmethod
    def tool_summarize_and_archive(max_lines: int = 50, llm=None) -> str:
        """原子工具4：记忆满载归档"""
        return MemoryCore.update_long_term_memory(max_lines=max_lines, llm=llm)

    @staticmethod
    def tool_write_diary(target_date: str = None, llm=None) -> str:
        """原子工具5：写日记（自动判断写哪天）"""
        if target_date:
            return MemoryCore.write_daily_diary(target_date, llm=llm)
        return MemoryCore.auto_write_diary(llm=llm)

#测试
# MemoryCore.memory_summarize("short_memories.md","memories.md",150)
