# 原子工具文档

## 1. read_file
读文件内容。

参数：filenames (列表) - 文件名列表
返回：文件内容字符串

## 2. write_file
写内容到文件。

参数：filename (字符串) - 文件名, content (字符串) - 内容
返回：操作结果

## 3. search_memory
搜索记忆。有日期则精准溯源，无日期则语义搜索。

参数：keyword (字符串) - 关键词, target_date (字符串, 可选) - 目标日期 (YYYY-MM-DD)
返回：搜索结果

## 4. summarize_and_archive
记忆满载归档。

参数：max_lines (整数, 可选) - 最大行数阈值，默认50
返回：总结结果

## 5. write_diary
写日记。有日期则写该日，无日期则自动检测。

参数：target_date (字符串, 可选) - 目标日期 (YYYY-MM-DD)
返回：日记写入结果