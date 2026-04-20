#!/usr/bin/env python3
"""
记忆系统闭环冒烟测试
测试三层流转：短期记忆RAM驻留、长期记忆自动打标入库、向量库条件触发检索、情绪缓动算法
"""

import asyncio
import json
import os
import sys
import tempfile
import shutil
import numpy as np
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# 添加backend目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# 强制离线模式，避免网络请求
os.environ['HF_HUB_OFFLINE'] = '1'

from core.emotion_engine import EmotionEngine
from core.vector_memory import VectorMemory
from core.memory_core import MemoryCore


class TestMemoryClosedLoop:
    """记忆系统闭环测试类"""

    def setup_method(self):
        """每个测试方法前的设置"""
        # 创建临时目录用于测试，避免污染真实数据
        self.temp_dir = tempfile.mkdtemp(prefix="agent_memory_test_")
        print(f"[测试] 使用临时目录: {self.temp_dir}")


    def teardown_method(self):
        """每个测试方法后的清理"""
        # 删除临时目录
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            print(f"[测试] 清理临时目录: {self.temp_dir}")

    def _mock_memory_root(self, memory_core_instance):
        """Mock MemoryCore实例的内存根目录为临时目录"""
        # 修改实例的_memory_root属性
        test_memory_root = Path(self.temp_dir) / "agent_memory"
        test_memory_root.mkdir(exist_ok=True)
        (test_memory_root / "long_term").mkdir(exist_ok=True)
        (test_memory_root / "vector_db").mkdir(exist_ok=True)

        memory_core_instance._memory_root = test_memory_root

    def _mock_vector_memory_root(self, vector_memory_instance):
        """Mock VectorMemory的向量存储目录为临时目录"""
        test_vector_root = Path(self.temp_dir) / "agent_memory" / "vector_db"
        test_vector_root.mkdir(parents=True, exist_ok=True)

        # 通过猴子补丁修改实例属性
        vector_memory_instance._vector_root = test_vector_root
        vector_memory_instance._index_path = test_vector_root / "faiss_index.index"
        vector_memory_instance._memory_path = test_vector_root / "vector_memory.json"

    async def test_emotion_engine_smooth_transition(self):
        """测试情绪缓动算法：平滑过渡、类型切换、自然衰减"""
        print("\n[测试] 情绪缓动算法")

        # 初始化情绪引擎
        engine = EmotionEngine(initial_type=0, initial_strength=0.0)

        # 测试1: 强度平滑（0.7旧 + 0.3新）
        engine.update_emotion(new_type=0, new_strength=10.0)
        type1, strength1 = engine.get_emotion()
        print(f"  第一次更新后: type={type1}, strength={strength1}")
        assert 0 <= strength1 <= 10, "强度应在0-10范围内"
        assert abs(strength1 - 2.7) < 0.01, "强度平滑算法错误"  # (0.7*0 + 0.3*10) * 0.9 = 2.7

        # 测试2: 类型切换阈值（差值≥2时切换）
        engine.update_emotion(new_type=2, new_strength=5.0)
        type2, strength2 = engine.get_emotion()
        print(f"  第二次更新（类型2，强度5）后: type={type2}, strength={strength2}")
        # 类型应从0切换到2，因为差值=2≥2
        assert type2 == 2, f"类型切换阈值失效，期望2，实际{type2}"

        # 测试3: 自然衰减（强度乘以0.9）
        prev_strength = strength2
        engine.update_emotion(new_type=2, new_strength=prev_strength)  # 相同强度
        type3, strength3 = engine.get_emotion()
        print(f"  第三次更新（相同类型/强度）后: type={type3}, strength={strength3}")
        assert abs(strength3 - (prev_strength * 0.9)) < 0.01, "自然衰减算法错误"

        # 测试4: 类型不切换（差值<2）
        engine.update_emotion(new_type=3, new_strength=8.0)  # 从2到3，差值=1<2
        type4, strength4 = engine.get_emotion()
        print(f"  第四次更新（类型3，强度8）后: type={type4}, strength={strength4}")
        assert type4 == 2, f"类型不应切换，期望2，实际{type4}"

        print("  [OK] 情绪缓动算法测试通过")

    async def test_short_term_memory_ram_persistence(self):
        """测试短期记忆RAM驻留与异步持久化"""
        print("\n[测试] 短期记忆RAM驻留")

        # 创建MemoryCore实例（传入llm_api=None）
        memory_core = MemoryCore(llm_api=None)

        # Mock内存根目录
        self._mock_memory_root(memory_core)

        # 初始短期记忆应为空
        initial_count = memory_core.get_short_term_count()
        assert initial_count == 0, f"初始短期记忆应为0，实际{initial_count}"

        # 添加短期记忆
        memory_core.add_short_term("user", "你好，今天天气怎么样？")
        memory_core.add_short_term("assistant", "今天天气晴朗，温度适宜。")

        # 检查RAM中的计数
        ram_count = memory_core.get_short_term_count()
        assert ram_count == 2, f"RAM中应有2条记忆，实际{ram_count}"

        # 获取格式化上下文
        context = memory_core.get_short_term_context()
        assert "用户: 你好，今天天气怎么样？" in context
        assert "助手: 今天天气晴朗，温度适宜。" in context

        # 等待异步持久化完成
        await asyncio.sleep(0.1)

        # 检查文件是否被写入
        short_term_path = memory_core._memory_root / "short_term.json"
        assert short_term_path.exists(), f"短期记忆文件未创建: {short_term_path}"

        # 读取文件内容验证
        with open(short_term_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert "dialogues" in data
        assert len(data["dialogues"]) == 2
        assert data["dialogues"][0]["role"] == "user"
        assert data["dialogues"][0]["content"] == "你好，今天天气怎么样？"

        print("  [OK] 短期记忆RAM驻留测试通过")

    async def test_long_term_storage_and_vector_sync(self):
        """测试长期记忆自动打标入库与向量同步（Mock LLM调用）"""
        print("\n[测试] 长期记忆入库与向量同步")

        # Mock SentenceTransformer 避免网络请求
        with patch('sentence_transformers.SentenceTransformer') as mock_st:
            # 创建 mock 模型
            mock_model = Mock()
            mock_model.encode.return_value = np.array([[0.1] * 384])  # 虚拟嵌入向量
            mock_st.return_value = mock_model

            # 创建Mock LLM API
            mock_llm_api = Mock()
            mock_llm_api.ask = Mock(return_value='''{
                "summary": "测试对话总结",
                "emotion_type": 2,
                "scene_type": "B",
                "importance": 8
            }''')

            # 创建MemoryCore实例，传入mock_llm_api
            memory_core = MemoryCore(llm_api=mock_llm_api)

            # Mock内存根目录
            self._mock_memory_root(memory_core)

            # 创建VectorMemory实例并mock其存储目录
            vector_memory = VectorMemory()
            self._mock_vector_memory_root(vector_memory)
            memory_core._vector_memory = vector_memory

            # 构建当前情绪字典（模拟高情绪场景）
            current_emotion_dict = {
                "type": 2,
                "strength": 8.0,
                "scene_type": "B"
            }

            # 模拟用户输入和AI回复（长度>25，满足入库条件）
            user_input = "这是一个测试对话，用于验证长期记忆存储功能是否正常工作。"
            ai_output = "这是一个测试回复，用于验证长期记忆存储功能是否正常工作。"

            # 直接调用内部方法（绕过条件检查）
            await memory_core._auto_tag_and_store(user_input, ai_output, current_emotion_dict)

            # 等待异步操作完成
            await asyncio.sleep(0.2)

            # 检查长期记忆文件是否创建
            date_str = datetime.now().strftime("%Y-%m-%d")
            long_term_path = memory_core._memory_root / "long_term" / f"{date_str}.json"
            assert long_term_path.exists(), f"长期记忆文件未创建: {long_term_path}"

            # 读取长期记忆内容
            with open(long_term_path, 'r', encoding='utf-8') as f:
                long_term_data = json.load(f)

            assert isinstance(long_term_data, list), "长期记忆文件应为列表"
            assert len(long_term_data) > 0, "长期记忆条目应至少有一条"

            last_entry = long_term_data[-1]
            assert last_entry["summary"] == "测试对话总结"
            assert last_entry["emotion_type"] == 2
            assert last_entry["scene_type"] == "B"
            assert last_entry["importance"] == 8

            # 检查向量映射文件是否创建（重要性>=5时应同步到向量库）
            vector_memory_path = vector_memory._memory_path
            assert vector_memory_path.exists(), f"向量映射文件未创建: {vector_memory_path}"

            # 读取向量映射内容
            with open(vector_memory_path, 'r', encoding='utf-8') as f:
                vector_data = json.load(f)

            assert isinstance(vector_data, list), "向量映射文件应为列表"
            assert len(vector_data) > 0, "向量映射条目应至少有一条"

            vector_entry = vector_data[-1]
            assert vector_entry["content"] == "测试对话总结"
            assert vector_entry["importance"] == 8

            print("  [OK] 长期记忆入库与向量同步测试通过")

    async def test_conditional_retrieve_gatekeeping(self):
        """测试条件触发检索的门控逻辑"""
        print("\n[测试] 条件触发检索门控")

        # Mock SentenceTransformer 避免网络请求
        with patch('sentence_transformers.SentenceTransformer') as mock_st:
            # 创建 mock 模型
            mock_model = Mock()
            mock_model.encode.return_value = np.array([[0.1] * 384])  # 虚拟嵌入向量
            mock_st.return_value = mock_model

            # 创建VectorMemory实例并mock存储目录
            vector_memory = VectorMemory()
            self._mock_vector_memory_root(vector_memory)

            # 预加载模型和索引（创建空索引）
            vector_memory._load_model_and_index()

            # 场景A: 低情绪强度（strength=2），应返回空列表
            result_low = vector_memory.conditional_retrieve(
                current_emotion_type=0,
                current_emotion_strength=2,  # <5
                current_scene_type="B",
                query_text="测试查询",
                top_k=3
            )
            assert result_low == [], f"低情绪强度应返回空列表，实际: {result_low}"

            # 场景B: 正确场景类型但情绪强度不足
            result_wrong_scene = vector_memory.conditional_retrieve(
                current_emotion_type=0,
                current_emotion_strength=8,  # ≥5
                current_scene_type="A",  # 不是B
                query_text="测试查询",
                top_k=3
            )
            assert result_wrong_scene == [], f"场景类型不为B应返回空列表，实际: {result_wrong_scene}"

            # 场景C: 情绪强度≥5且场景类型为B，但索引为空，也应返回空列表
            result_empty_index = vector_memory.conditional_retrieve(
                current_emotion_type=0,
                current_emotion_strength=8,  # ≥5
                current_scene_type="B",  # 是B
                query_text="测试查询",
                top_k=3
            )
            assert result_empty_index == [], f"空索引应返回空列表，实际: {result_empty_index}"

            print("  [OK] 条件触发检索门控测试通过")

    async def test_full_closed_loop(self):
        """完整闭环测试：从短期记忆到长期存储再到条件检索"""
        print("\n[测试] 完整闭环流转")

        # Mock SentenceTransformer 避免网络请求
        with patch('sentence_transformers.SentenceTransformer') as mock_st:
            # 创建 mock 模型
            mock_model = Mock()
            mock_model.encode.return_value = np.array([[0.1] * 384])  # 虚拟嵌入向量
            mock_st.return_value = mock_model

            # 创建Mock LLM API
            mock_llm_api = Mock()
            mock_llm_api.ask = Mock(return_value='''{
                "summary": "完整闭环测试总结",
                "emotion_type": 1,
                "scene_type": "B",
                "importance": 9
            }''')

            # 创建MemoryCore实例
            memory_core = MemoryCore(llm_api=mock_llm_api)

            # Mock内存根目录
            self._mock_memory_root(memory_core)

            # 创建VectorMemory实例并mock存储目录
            vector_memory = VectorMemory()
            self._mock_vector_memory_root(vector_memory)
            memory_core._vector_memory = vector_memory

            # 步骤1: 添加短期记忆
            memory_core.add_short_term("user", "这是一个完整的闭环测试输入，用于验证记忆系统的三层流转。")
            memory_core.add_short_term("assistant", "这是一个完整的闭环测试回复，用于验证记忆系统的三层流转。")

            # 步骤2: 更新情绪状态到高情绪
            emotion_dict = memory_core.update_and_get_emotion(new_type=1, new_strength=9.0)
            emotion_dict["scene_type"] = "B"  # 手动添加scene_type

            # 步骤3: 触发长期记忆存储（满足条件：情绪强度≥5且场景类型为B）
            user_input = "这是一个完整的闭环测试输入，用于验证记忆系统的三层流转。"
            ai_output = "这是一个完整的闭环测试回复，用于验证记忆系统的三层流转。"

            # 直接调用内部方法，绕过条件检查
            await memory_core._auto_tag_and_store(user_input, ai_output, emotion_dict)

            # 等待异步操作完成
            await asyncio.sleep(0.3)

            # 步骤4: 验证向量库中已有记忆
            vector_memory._load_model_and_index()
            assert vector_memory._index is not None
            assert vector_memory._index.ntotal > 0, "向量索引中应有条目"

            # 步骤5: 测试条件触发检索（应能检索到刚存入的记忆）
            retrieved = vector_memory.conditional_retrieve(
                current_emotion_type=1,
                current_emotion_strength=9,  # ≥5
                current_scene_type="B",  # 是B
                query_text="闭环测试",
                top_k=3
            )

            assert len(retrieved) > 0, "条件检索应返回结果"

            # 验证检索结果内容
            first_result = retrieved[0]
            assert "完整闭环测试总结" in first_result.get("content", "")
            assert first_result.get("emotion_type") == 1
            assert first_result.get("scene_type") == "B"

            print("  [OK] 完整闭环流转测试通过")


async def main():
    """主测试函数"""
    print("=" * 60)
    print("记忆系统闭环冒烟测试")
    print("=" * 60)

    tester = TestMemoryClosedLoop()

    # 执行测试
    tests = [
        ("情绪缓动算法", tester.test_emotion_engine_smooth_transition),
        ("短期记忆RAM驻留", tester.test_short_term_memory_ram_persistence),
        ("长期记忆入库与向量同步", tester.test_long_term_storage_and_vector_sync),
        ("条件触发检索门控", tester.test_conditional_retrieve_gatekeeping),
        ("完整闭环流转", tester.test_full_closed_loop),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            tester.setup_method()
            await test_func()
            print(f"[OK] {test_name} 通过")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test_name} 失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            tester.teardown_method()

    print("\n" + "=" * 60)
    print(f"测试完成: {passed}/{total} 通过")

    if passed == total:
        print("[PASS] 所有测试通过！记忆系统三层流转功能正常。")
        return 0
    else:
        print("[FAIL] 部分测试失败，请检查实现。")
        return 1


if __name__ == "__main__":
    # 运行测试
    exit_code = asyncio.run(main())
    sys.exit(exit_code)