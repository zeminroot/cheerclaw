---
name: memory
description: 双层记忆系统，基于 grep 检索召回记忆信息。
always: true
---

# 记忆
## 结构
- workspace目录下`origin/origin_qas.jsonl` — 最原始完整的交互日志。被截断，仅加载截断点之后的信息到上下文中。
- workspace目录下`memory/HISTORY.md` — 仅追加的事件日志。origin_qas.jsonl中截断点之前的事件摘要。不加载到上下文中。在需要历史记忆信息时使用 grep 风格工具搜索 或者 将历史信息加载到内存中过滤搜索。每条记录以 [YYYY-MM-DD HH:MM] 开头。
- workspace目录下`memory/MEMORY.md` — 精简的长期重要事实信息（个人信息、偏好、等）。始终加载到你的上下文中。

## 搜索历史记忆（渐进式搜索）
优先使用 `exec` 工具进行关键字定向搜索`memory/HISTORY.md`获取大致信息和时间点。
如果搜索到的大致信息已经足够则直接使用。
如果搜索到的大致信息不够则扩大范围继续搜索或加`时间点`作为关键字搜索`origin/origin_qas.jsonl`。
在搜索过程中可以渐进式地扩大搜索范围，但**禁止一次性读取`memory/HISTORY.md`或`origin/origin_qas.jsonl`全部信息到大模型上下文中**。
搜索示例：
- **Linux/macOS：** `grep -i "keyword" memory/HISTORY.md`
- **Windows：** `findstr /i "keyword" memory\HISTORY.md`
- **跨平台 Python：** `python3 -c "from pathlib import Path; text = Path('memory/HISTORY.md').read_text(encoding='utf-8'); print('\n'.join([l for l in text.splitlines() if 'keyword' in l.lower()][-20:]))"`

## 何时更新 MEMORY.md
使用 `edit_file` 或 `write_file` 立即写入重要事实：
- 用户偏好（"我喜欢深色模式"）
- 个人画像信息（"用户名叫 Alice "）

## 自动整合
当会话变得很大时，截断点之前的旧对话会自动汇总并追加到 HISTORY.md。长期重要事实会被提取到 MEMORY.md。你无需管理此过程。