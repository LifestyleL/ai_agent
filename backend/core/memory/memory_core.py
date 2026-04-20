"""
重构后的记忆系统核心模块
实现短期记忆 RAM 驻留、情绪联动、长期记忆自动打标入库
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# 添加父目录到sys.path以便导入config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.emotion.emotion_engine import EmotionEngine
import config
from core.llm.llm_api import LLMAPI


class MemoryCore:
    """记忆系统核心类，管理短期记忆、情绪状态和长期记忆存储"""

    # 配置（将在__init__中根据config动态设置）

    def __init__(self, llm_api: Optional[LLMAPI] = None, vector_memory: Optional[Any] = None):
        """
        初始化记忆系统
        :param llm_api: LLMAPI实例，如果为None则自动创建DeepSeek实例
        :param vector_memory: VectorMemory实例，如果为None则自动创建
        """
        # 短期记忆缓冲区（RAM驻留）
        self._short_term_buffer: List[Dict[str, str]] = []

        # 短期记忆容量配置
        self._short_term_capacity_base = config.SHORT_TERM_CAPACITY_BASE
        self._short_term_capacity_dynamic = config.SHORT_TERM_CAPACITY_DYNAMIC
        self._short_term_capacity_max = config.SHORT_TERM_CAPACITY_MAX
        self._engagement_score = 0.5  # 默认参与度分数（0.0-1.0）

        # 计算当前容量
        self.max_short_term_turns = self._calculate_short_term_capacity()

        # 情绪引擎
        self._emotion_engine = EmotionEngine()

        # LLM API实例（用于自动打标）
        self._llm_api = llm_api
        if self._llm_api is None:
            if config.DEEPSEEK_API_KEY:
                self._llm_api = LLMAPI(
                    api_key=config.DEEPSEEK_API_KEY,
                    base_url=config.DEEPSEEK_BASE_URL,
                    model=config.DEEPSEEK_MODEL
                )
            else:
                print("[WARN] DeepSeek API密钥未配置，自动打标功能将不可用")

        # 向量记忆实例（根据配置启用/禁用）
        self._vector_memory = None
        if config.ENABLE_VECTOR_MEMORY:
            try:
                from .vector_memory import VectorMemory
                self._vector_memory = VectorMemory()
                print("[MemoryCore] 向量记忆模块已启用")
            except ImportError as e:
                print(f"[WARN] 无法导入VectorMemory模块: {e}")
            except Exception as e:
                print(f"[WARN] 初始化VectorMemory失败: {e}")
        else:
            print("[MemoryCore] 向量记忆模块已禁用 (V3.0默认配置)")

        # 记忆存储根目录
        self._memory_root = Path(__file__).parent.parent / "agent_memory"
        self._memory_root.mkdir(exist_ok=True)
        (self._memory_root / "long_term").mkdir(exist_ok=True)
        # vector_db 目录已迁移至 vector_db_v1_deprecated/（V3.0 暂不启用）

        # 加载现有的短期记忆
        self._load_short_term_from_disk()

    def _calculate_short_term_capacity(self) -> int:
        """
        计算短期记忆动态容量
        根据参与度分数动态调整，高质量对话保留更多记忆
        """
        if not self._short_term_capacity_dynamic:
            return self._short_term_capacity_base

        # 根据参与度分数调整容量 (0.0-1.0)
        # 参与度越高，容量越大
        capacity_factor = 0.5 + self._engagement_score  # 0.5-1.5倍
        adjusted = int(self._short_term_capacity_base * capacity_factor)

        # 限制在最大容量范围内
        return min(max(self._short_term_capacity_base, adjusted), self._short_term_capacity_max)

    def update_engagement_score(self, score: float) -> None:
        """
        更新参与度分数 (0.0-1.0)
        可由外部调用，基于对话质量、长度、情感互动等评估
        """
        # 平滑更新
        self._engagement_score = 0.7 * self._engagement_score + 0.3 * max(0.0, min(1.0, score))
        # 重新计算容量
        self.max_short_term_turns = self._calculate_short_term_capacity()

    def add_short_term(self, role: str, content: str) -> None:
        """
        添加短期记忆对话，异步持久化到磁盘
        :param role: 角色，'user' 或 'assistant'
        :param content: 对话内容
        """
        # 去重检查：防止同一条消息被写两次（防未来重复）
        if self._short_term_buffer:
            last = self._short_term_buffer[-1]
            if (last.get("role") == role and
                last.get("content") == content):
                print(f"[短期记忆] 去重跳过：与上一条完全相同的{role}消息")
                return  # 跳过写入

        # 添加到内存缓冲区
        dialogue = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        self._short_term_buffer.append(dialogue)

        # 如果超出最大轮数，移除最旧的一条
        if len(self._short_term_buffer) > self.max_short_term_turns:
            self._short_term_buffer.pop(0)

        # 异步触发持久化（不阻塞主逻辑）
        asyncio.create_task(self._persist_short_term())

    def get_short_term_context(self, max_turns: Optional[int] = None) -> str:
        """
        获取格式化后的短期记忆上下文，用于塞给LLM
        :param max_turns: 最多返回的对话轮数，默认返回全部
        :return: 格式化后的对话字符串
        """
        if not self._short_term_buffer:
            return ""

        buffer = self._short_term_buffer
        if max_turns is not None and max_turns > 0:
            buffer = buffer[-max_turns:]

        formatted = []
        for dialogue in buffer:
            role = "用户" if dialogue["role"] == "user" else "助手"
            formatted.append(f"{role}: {dialogue['content']}")

        return "\n".join(formatted)

    async def _persist_short_term(self) -> None:
        """异步将短期记忆持久化到JSON文件"""
        try:
            # 构建存储结构
            data = {
                "dialogues": self._short_term_buffer,
                "current_emotion": self._emotion_engine.get_emotion_dict(),
                "updated_at": datetime.now().isoformat()
            }

            # 使用asyncio.to_thread避免阻塞事件循环
            await asyncio.to_thread(self._write_json, self._memory_root / "short_term.json", data)

        except Exception as e:
            print(f"[ERROR] 短期记忆持久化失败: {e}")

    def _load_short_term_from_disk(self) -> None:
        """从磁盘加载短期记忆"""
        short_term_path = self._memory_root / "short_term.json"
        if not short_term_path.exists():
            return

        try:
            data = self._read_json(short_term_path)

            # 恢复对话记录
            if "dialogues" in data and isinstance(data["dialogues"], list):
                self._short_term_buffer = data["dialogues"]
                # 确保不超过最大限制
                if len(self._short_term_buffer) > self.max_short_term_turns:
                    self._short_term_buffer = self._short_term_buffer[-self.max_short_term_turns:]

            # 恢复情绪状态
            if "current_emotion" in data:
                emotion = data["current_emotion"]
                if "type" in emotion and "strength" in emotion:
                    self._emotion_engine.reset(emotion["type"], emotion["strength"])

        except Exception as e:
            print(f"[WARN] 加载短期记忆失败: {e}")
            self._short_term_buffer = []

    def update_and_get_emotion(self, new_type: int, new_strength: float) -> Dict[str, Any]:
        """
        更新情绪状态并返回最新的情绪字典
        :param new_type: 新情绪类型 (0-3)
        :param new_strength: 新情绪强度 (0-10)
        :return: 当前情绪状态字典
        """
        self._emotion_engine.update_emotion(new_type, new_strength)
        return self._emotion_engine.get_emotion_dict()

    def get_current_emotion(self) -> Dict[str, Any]:
        """获取当前情绪状态"""
        return self._emotion_engine.get_emotion_dict()

    # V3.0 暂不启用长期记忆存储功能
    # def trigger_long_term_storage(self, user_input: str, ai_output: str, current_emotion_dict: Dict[str, Any]) -> None:
    #     pass

    # V3.0 暂不启用自动打标与存储
    # async def _auto_tag_and_store(self, user_input: str, ai_output: str, current_emotion_dict: Dict[str, Any]) -> None:
    #     pass

    # V3.0 暂不启用LLM打标功能
    # async def _call_llm_for_tagging(self, user_input: str, ai_output: str) -> Optional[Dict[str, Any]]:
    #     return None

    # V3.0 暂不启用长期记忆追加功能
    # async def _append_to_long_term(self, memory_entry: Dict[str, Any]) -> None:
    #     pass

    # 同步文件操作辅助方法（在子线程中运行）
    def _write_json(self, file_path: Path, data: Any) -> None:
        """原子写入JSON文件，支持错误恢复"""
        import tempfile
        import shutil

        # 创建备份（如果文件已存在）
        backup_path = None
        if file_path.exists():
            backup_path = file_path.with_suffix('.json.bak')
            try:
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                print(f"[WARN] 创建备份失败 {file_path}: {e}")

        # 写入临时文件
        temp_file = None
        try:
            # 创建临时文件在同一目录
            temp_fd, temp_path = tempfile.mkstemp(dir=file_path.parent, suffix='.tmp')
            temp_file = os.fdopen(temp_fd, 'w', encoding='utf-8')
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()

            # 原子重命名
            shutil.move(temp_path, file_path)
            print(f"[MemoryCore] 已原子写入: {file_path}")

            # 成功写入后删除备份
            if backup_path and backup_path.exists():
                try:
                    os.remove(backup_path)
                except Exception as e:
                    print(f"[WARN] 删除备份失败: {e}")

        except Exception as e:
            print(f"[ERROR] 原子写入失败 {file_path}: {e}")

            # 尝试恢复备份
            if backup_path and backup_path.exists() and not file_path.exists():
                try:
                    shutil.copy2(backup_path, file_path)
                    print(f"[MemoryCore] 已从备份恢复: {file_path}")
                except Exception as restore_error:
                    print(f"[ERROR] 备份恢复失败: {restore_error}")

            # 清理临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

            raise  # 重新抛出异常

    def _read_json(self, file_path: Path) -> Any:
        """同步读取JSON文件，支持从备份恢复"""
        import shutil

        # 尝试读取主文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 读取JSON失败 {file_path}: {e}")

            # 尝试从备份恢复
            backup_path = file_path.with_suffix('.json.bak')
            if backup_path.exists():
                try:
                    print(f"[MemoryCore] 尝试从备份恢复: {backup_path}")
                    # 复制备份到主文件
                    shutil.copy2(backup_path, file_path)
                    # 再次尝试读取
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as backup_error:
                    print(f"[ERROR] 备份恢复失败: {backup_error}")

            # 如果还是失败，返回空数据
            print(f"[MemoryCore] 无法读取 {file_path}，返回空数据")
            return {}

    def clear_short_term(self) -> None:
        """清空短期记忆"""
        self._short_term_buffer.clear()
        # 异步更新磁盘
        asyncio.create_task(self._persist_short_term())

    def get_short_term_count(self) -> int:
        """获取短期记忆条目数量"""
        return len(self._short_term_buffer)

    # V3.0 暂不启用规则打标功能
    # def _quick_rule_tag(self, user_input: str, ai_output: str) -> Dict[str, Any]:
    #     return {"emotion_type": 0, "emotion_strength": 2, "scene_type": "A"}

    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计信息（V3.0 仅保留短期记忆）"""
        return {
            "short_term_count": len(self._short_term_buffer),
            "long_term_count_today": 0,  # V3.0 暂不启用长期记忆
            "emotion": self._emotion_engine.get_emotion_dict(),
            "max_short_term_turns": self.max_short_term_turns
        }

    # ==================== V3 标准读取方法 ====================
    def load_personality(self) -> str:
        """加载人设文件（V3 标准方法）"""
        path = self._memory_root / "personality.md"
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"[WARN] 加载人设文件失败: {e}")
        return ""

    def load_mood_templates(self) -> str:
        """加载心情模板（V3 标准方法）"""
        path = self._memory_root / "mood_blank.md"
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"[WARN] 加载心情模板失败: {e}")
        return ""

    def load_tools_index(self) -> str:
        """加载工具索引（V3 标准方法）"""
        path = self._memory_root / "tools" / "tools_index.md"
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"[WARN] 加载工具索引失败: {e}")
        return ""

    def get_random_long_term_memory_v3(self, count: int = 1) -> str:
        """获取随机长期记忆片段（V3：从日记索引获取）"""
        try:
            # 尝试从日记目录读取最近的日记
            diary_dir = self._memory_root / "diary" / "daily"
            if diary_dir.exists():
                files = list(diary_dir.glob("*.md"))
                files.sort(key=lambda x: x.stat().st_mtime if x.is_file() else 0)
                if files:
                    import random
                    # 最近3天
                    recent_files = files[-3:] if len(files) >= 3 else files
                    target = random.choice(recent_files)
                    with open(target, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 返回前 200 字
                    return content[:200]
        except Exception as e:
            print(f"[WARN] 获取随机长期记忆失败: {e}")
        return ""

    # ==================== 兼容性静态方法（逐步迁移） ====================
    @staticmethod
    def append_to_file(filename: str, content: str) -> None:
        """兼容性方法：空实现（V3 保留兼容性，不再打印警告）"""
        # 不再追加文件，避免破坏新系统
        pass

    @staticmethod
    def load_files(filenames: list[str]) -> str:
        """兼容性方法：实际读取文件内容（V3 保留兼容性，不再打印警告）"""
        if not filenames:
            return ""
        # 记忆根目录：backend/agent_memory
        memory_root = Path(__file__).parent.parent / "agent_memory"
        result = []
        for name in filenames:
            name = name.strip()
            # 处理工具路径
            if name.startswith("tools/"):
                path = memory_root / name
            else:
                path = memory_root / name
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    result.append(content)
                except Exception as e:
                    print(f"[WARN] 兼容性加载 {name} 失败: {e}")
                    result.append("")
            else:
                # 文件不存在，返回空字符串
                pass
        # 返回第一个文件的内容（保持旧行为）
        return result[0] if result else ""

    @staticmethod
    def get_random_long_term_memory(n: int = 3) -> str:
        """兼容性方法：实际读取随机日记片段（V3 保留兼容性，不再打印警告）"""
        try:
            # 记忆根目录：backend/agent_memory
            memory_root = Path(__file__).parent.parent / "agent_memory"
            diary_dir = memory_root / "diary" / "daily"
            if diary_dir.exists():
                import random
                files = list(diary_dir.glob("*.md"))
                files.sort(key=lambda x: x.stat().st_mtime if x.is_file() else 0)
                if files:
                    # 最近3天
                    recent_files = files[-3:] if len(files) >= 3 else files
                    target = random.choice(recent_files)
                    with open(target, 'r', encoding='utf-8') as f:
                        content = f.read()
                    # 返回前 200 字
                    return content[:200]
        except Exception as e:
            # 静默失败
            pass
        return ""

    @staticmethod
    def set_short_term_memory_cache(history: list) -> None:
        """兼容性方法：空实现"""
        pass

    @staticmethod
    def clear_file(filename: str, backup: bool = True) -> str:
        """兼容性方法：空实现（V3 保留兼容性，不再打印警告）"""
        # 不再清空文件，避免破坏新系统
        return ""

    @staticmethod
    def write_file(filename: str, content: str) -> None:
        """兼容性方法：空实现（V3 保留兼容性，不再打印警告）"""
        # 不再写入文件，避免破坏新系统
        pass