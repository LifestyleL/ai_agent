"""
Phase 3 验证：Skill 系统热插拔

5 个场景：
  1. load_all() 加载 3 个 .md 技能，验证数量
  2. 关键词匹配："帮我写个日记" → write_diary
  3. LLM 语义匹配："我想回顾一下" → search_memory
  4. 热卸载：unload("write_diary") 后匹配返回空
  5. 完整流水线：skill_experience 出现在 system_prompt

用法:
  cd backend
  python tests/manual/test_skill_system.py              # mock LLM
  python tests/manual/test_skill_system.py --live        # real LLM
"""

import asyncio
import sys
import os

_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _project_root)
sys.path.insert(0, _backend_dir)

from backend.core.skill.skill_manager import SkillManager
from backend.core.skill.skill_loader import Skill, SkillLoader
from backend.plugins.registry import ToolRegistry
from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.prompt_build import PromptBuildStage
from backend.core.think_pipeline.skill_match_stage import SkillMatchStage


# ═══════════════════════════════════════════════════════════════
# Mock LLM（不依赖 API Key）
# ═══════════════════════════════════════════════════════════════

class MockLLM:
    def __init__(self, scenario="normal"):
        self.scenario = scenario

    async def ask_with_system_async(self, system_prompt, user_input, temperature=0):
        # 从分类 prompt 中提取用户原始输入（格式: 用户输入: "..."）
        import re
        m = re.search(r'用户输入:\s*"(.+?)"', user_input)
        text = m.group(1) if m else user_input
        text_lower = text.lower()
        # 模拟 LLM 语义匹配（只看用户消息，不看技能列表）
        if "回顾" in text_lower or "以前" in text_lower or "聊过" in text_lower:
            return "search_memory"
        if "日记" in text_lower or "记录" in text_lower:
            return "write_diary"
        if "文件" in text_lower or "查看" in text_lower:
            return "read_file"
        if self.scenario == "always_none":
            return "NONE"
        if self.scenario == "timeout":
            raise asyncio.TimeoutError("mock timeout")
        return "NONE"


# ═══════════════════════════════════════════════════════════════
# 测试场景
# ═══════════════════════════════════════════════════════════════

async def test_load_all():
    """场景 1：加载全部技能"""
    print(f"\n{'─' * 50}")
    print("[场景1] load_all() 加载验证")

    mgr = SkillManager()
    count = mgr.load_all()
    skills = mgr.active_skills

    print(f"  加载数量: {count}")
    for name, skill in skills.items():
        print(f"  - {name}: {skill.description} | tools={skill.tools}")

    ok = count == 3 and "search_memory" in skills and "write_diary" in skills and "read_file" in skills
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok, mgr


async def test_keyword_match():
    """场景 2：关键词匹配"""
    print(f"\n{'─' * 50}")
    print("[场景2] 关键词匹配: '帮我写个日记'")

    mgr = SkillManager()  # no LLM → 纯关键词
    mgr.load_all()

    result = await mgr.match("帮我写个日记吧")
    print(f"  匹配结果: {result[:100] if result else '(空)'}")

    ok = result and "write_diary" in result
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_llm_match():
    """场景 3：LLM 语义匹配"""
    print(f"\n{'─' * 50}")
    print("[场景3] LLM 语义匹配: '我想回顾一下以前聊过的事情'")

    llm = MockLLM()
    mgr = SkillManager(llm=llm)
    mgr.load_all()

    result = await mgr.match("我想回顾一下以前聊过的事情")
    print(f"  匹配结果: {result[:100] if result else '(空)'}")

    ok = result and "search_memory" in result
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_hot_unload():
    """场景 4：热卸载"""
    print(f"\n{'─' * 50}")
    print("[场景4] 热卸载: unload('write_diary')")

    llm = MockLLM()
    mgr = SkillManager(llm=llm)
    mgr.load_all()

    # 卸载前应匹配
    before = await mgr.match("帮我写个日记")
    print(f"  卸载前匹配: {'write_diary' in before}")

    # 卸载
    result = mgr.unload_skill("write_diary")
    print(f"  unload 返回: {result}")

    # 卸载后不应匹配
    after = await mgr.match("帮我写个日记")
    print(f"  卸载后匹配: {after[:100] if after else '(空)'}")

    ok = result and "write_diary" in before and not after
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_pipeline_integration():
    """场景 5：完整流水线 — skill_experience 注入 system_prompt"""
    print(f"\n{'─' * 50}")
    print("[场景5] 流水线集成: SkillMatchStage → PromptBuildStage")

    llm = MockLLM()
    mgr = SkillManager(llm=llm)
    mgr.load_all()

    # 模拟管线流程
    ctx = ThinkContext(user_input="我想回顾一下以前聊过的内容")

    # Stage 1: SkillMatch
    match_stage = SkillMatchStage(skill_manager=mgr)
    ctx = await match_stage.process(ctx)
    print(f"  skill_experience ({len(ctx.memory_context.get('skill_experience', ''))} chars): "
          f"{ctx.memory_context.get('skill_experience', '')[:80]}...")

    # Stage 2: PromptBuild
    prompt_stage = PromptBuildStage()
    ctx = await prompt_stage.process(ctx)
    sp = ctx.system_prompt

    has_skills_tag = "<skills>" in sp
    has_skill_content = "search_memory" in sp
    print(f"  system_prompt 含 <skills> 标签: {has_skills_tag}")
    print(f"  system_prompt 含技能内容: {has_skill_content}")

    ok = has_skills_tag and has_skill_content
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_llm_fallback():
    """场景 6：LLM 超时/异常 → 降级关键词"""
    print(f"\n{'─' * 50}")
    print("[场景6] LLM 超时降级关键词")

    llm = MockLLM(scenario="timeout")
    mgr = SkillManager(llm=llm)
    mgr.load_all()

    result = await mgr.match("帮我写个日记")
    print(f"  降级匹配结果: {result[:100] if result else '(空)'}")

    ok = result and "write_diary" in result
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_no_match():
    """场景 7：无匹配技能"""
    print(f"\n{'─' * 50}")
    print("[场景7] 无匹配: '今天天气真好'")

    llm = MockLLM(scenario="always_none")
    mgr = SkillManager(llm=llm)
    mgr.load_all()

    result = await mgr.match("今天天气真好")
    print(f"  结果: {result if result else '(空)'}")

    ok = result == ""
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_live_match():
    """使用真实 LLM 测试语义匹配"""
    print(f"\n{'─' * 50}")
    print("[Live] 真实 LLM 语义匹配")

    try:
        from backend.core.llm.llm_factory import LLMFactory
        llm = LLMFactory.get_default()
    except Exception as e:
        print(f"  跳过: LLM 不可用 ({e})")
        return True  # 不算失败

    mgr = SkillManager(llm=llm)
    mgr.load_all()

    # 测试几个变体
    tests = [
        ("我想回顾一下以前聊过的事情", "search_memory"),
        ("帮我写个日记记录今天", "write_diary"),
        ("看看那个文件里写了什么", "read_file"),
        ("今天天气真好", None),  # 不应匹配
    ]

    all_ok = True
    for user_input, expected in tests:
        result = await mgr.match(user_input)
        matched_name = ""
        if result and "### " in result:
            matched_name = result.split("### ")[1].split("\n")[0]
        status = "?"
        if expected:
            ok = expected in result if result else False
            status = "PASS" if ok else "FAIL"
        else:
            ok = result == ""
            status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{status}] '{user_input}' → {matched_name or '(无)'}")

    print(f"  {'[PASS] 全部通过' if all_ok else '[FAIL] 部分失败'}")
    return all_ok


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

async def main():
    use_live = "--live" in sys.argv

    print("=" * 50)
    print("Phase 3: Skill 系统热插拔验证")
    print(f"模式: {'真实 LLM' if use_live else 'Mock LLM'}")
    print("=" * 50)

    results = []

    # Mock tests always run
    results.append(await test_load_all())
    if isinstance(results[-1], tuple):
        results[-1] = results[-1][0]  # unpack (bool, mgr)

    results.append(await test_keyword_match())
    results.append(await test_llm_match())
    results.append(await test_hot_unload())
    results.append(await test_pipeline_integration())
    results.append(await test_llm_fallback())
    results.append(await test_no_match())

    if use_live:
        results.append(await test_live_match())

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"结果: {passed}/{total} 通过")
    if passed < total:
        print("[FAIL] 部分场景失败，请检查输出")
    else:
        print("[PASS] 全部通过")


if __name__ == "__main__":
    asyncio.run(main())
