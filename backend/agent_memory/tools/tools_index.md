# 原子工具索引

## 5个原子工具

1. read_file - 读文件内容（替代 load_memory）
2. write_file - 写内容到文件（替代 update_memory、create_file、clear_file）
3. search_memory - 统一搜索入口（有日期精准溯源，无日期语义搜索）
4. summarize_and_archive - 记忆满载归档（替代 update_long_term_memory）
5. write_diary - 写日记（有日期写该日，无日期自动检测）

## 使用说明

1. **查询流程**：
   - 先查看本索引了解原子工具
   - 如需详细使用说明，查询tool_docs.md获取完整文档
   - 调用read_file(["tools/tool_docs.md"])查看具体工具的详细说明

2. **场景建议**：
   - 用户提到"睡觉"、"结束对话"、"明天见" → 使用write_diary()
   - 用户要求"总结记忆" → 使用summarize_and_archive(max_lines=10)
   - 用户询问过去的事情 → 使用search_memory(keyword)
   - 用户提供新信息需要记录 → 使用write_file(filename, content)

3. **注意事项**：
   - 每个工具最多调用1次，除非有明确需要重试的原因
   - 删除操作已内嵌到write_file（通过内容清空）
   - 复杂判断由代码处理，DeepSeek只管传参

## 版本信息
- 最后更新: 2026-04-14
- 工具总数: 5个原子工具
- 设计理念: 极简降维，消灭选择冗余