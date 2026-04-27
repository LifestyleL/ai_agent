---
name: read_file
description: 读取本地文件内容
auto_execute: false
keywords:
  - 读取
  - 看看
  - 打开
  - 文件内容
  - 什么内容
  - 查看文件
  - 显示文件
tools:
  - read_file
---

## 触发判断
用户想查看某个文件的内容时触发。

## 参数决策
- filepath：用户可能给相对路径或文件名，优先按原样传入
  如果用户说"看看配置文件"，需要先 list_directory 确认路径

## 常见误区
- 不要猜测文件路径，不确定时先 list_directory
- 大文件（>100行）只读取前 50 行，提示用户可以指定范围