import asyncio
from typing import List, Dict, Any
from backend.plugins.base_skill import BaseSkill
from backend.plugins.base_tool import BaseTool


class MemorySummarySkill(BaseSkill):
    """静态编排 Skill 示例：记忆总结与归档"""
    name = "memory_summary_skill"
    description = "搜索近期记忆，拼接后写入归档文件"

    # 声明依赖的工具名称，方便外部注入时核对
    required_tool_names = ["search_memory", "write_file"]

    def __init__(self, tools: List[BaseTool]):
        super().__init__(tools)
        # 从传入的 tools 列表中按名字提取出来，方便后续调用
        self.search_tool = next((t for t in tools if t.name == "search_memory"), None)
        self.write_tool = next((t for t in tools if t.name == "write_file"), None)

        if not self.search_tool or not self.write_tool:
            raise ValueError("MemorySummarySkill 缺少必要的依赖工具！")

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行静态编排流程。
        context 预期格式: {"query": "搜索关键词", "archive_path": "data/archive.txt"}
        """
        query = context.get("query", "最近的重要对话")
        archive_path = context.get("archive_path", "agent_memory/test_skill_output.txt")

        print(f"[Skill] 开始执行记忆总结，查询: {query}")

        try:
            # 步骤 1：调用搜索工具 (由于原有工具是同步的，使用 to_thread 防止阻塞)
            search_result_dict = await asyncio.to_thread(
                self.search_tool.execute, keyword=query
            )
            print(f"[Skill] 搜索完成: {search_result_dict}")

            # 步骤 2：简单处理数据（实际业务中这里可能是字符串拼接或提取）
            # 这里做个简单的模拟拼接
            mock_summary = f"归档摘要：基于 '{query}' 的搜索结果。\n"
            if "result" in search_result_dict:
                mock_summary += f"搜索结果: {str(search_result_dict['result'])[:100]}..."

            # 步骤 3：调用写文件工具归档
            write_result_dict = await asyncio.to_thread(
                self.write_tool.execute, filename=archive_path, content=mock_summary
            )
            print(f"[Skill] 归档完成: {write_result_dict}")

            return {
                "success": True,
                "message": "记忆总结与归档 Skill 执行成功",
                "search_result": search_result_dict,
                "archive_result": write_result_dict
            }

        except Exception as e:
            print(f"[Skill] 执行失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}