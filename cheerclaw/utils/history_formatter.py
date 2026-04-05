#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   history_formatter.py
@Author  :   zemin
@Desc    :   将对话历史格式化为可读的展示字符串
'''

import json


# 角色对应的图标
ROLE_ICONS = {
    "user": "👤",
    "assistant": "🤖",
    "tool": "🔧",
}


def format_history_for_display(
    visible_history: list[dict],
    compress_idx: int,
    total_count: int,
    max_content_length: int = 200,
    max_args_length: int = 100,
) -> str:
    """
    将对话历史格式化为展示字符串

    参数：
        visible_history: 可见的历史消息列表（压缩点之后）
        compress_idx: 压缩点索引
        total_count: 历史消息总数
        max_content_length: 内容最大长度，超过则截断
        max_args_length: 工具参数最大长度，超过则截断

    返回：
        格式化后的展示字符串
    """
    if not visible_history:
        return "📭 当前没有对大模型可见的对话历史"

    lines = [
        f"📜 对话历史（压缩点: {compress_idx}，可见消息: {len(visible_history)}/{total_count} 条）\n"
    ]

    for i, msg in enumerate(visible_history, start=compress_idx):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")

        icon = ROLE_ICONS.get(role, "❓")

        # 如果有工具调用，展示工具信息
        if tool_calls and role == "assistant":
            tool_lines = _format_assistant_with_tools(
                i, icon, role, content, tool_calls, max_content_length, max_args_length
            )
            lines.extend(tool_lines)
        else:
            # 普通消息或工具结果
            line = _format_regular_message(i, icon, role, content, msg, max_content_length)
            lines.append(line)

    return "\n".join(lines)


def _format_assistant_with_tools(
    idx: int,
    icon: str,
    role: str,
    content: str,
    tool_calls: list,
    max_content_length: int,
    max_args_length: int,
) -> list[str]:
    """
    格式化包含工具调用的助手消息
    """
    lines = [f"[{idx}] {icon} {role}:"]

    if content:
        content_display = content[:max_content_length]
        if len(content) > max_content_length:
            content_display += "..."
        lines.append(f"    {content_display}")

    for tc in tool_calls:
        tc_name, tc_args_str = _extract_tool_call_info(tc, max_args_length)
        lines.append(f"    └─ 📎 {tc_name}({tc_args_str})")

    return lines


def _format_regular_message(
    idx: int,
    icon: str,
    role: str,
    content: str,
    msg: dict,
    max_content_length: int,
) -> str:
    # 工具结果特殊处理
    if role == "tool":
        tool_name = msg.get("name", "unknown")
        content = f"[工具: {tool_name}] {content}"

    # 截断过长的内容
    if len(content) > max_content_length:
        content = content[:max_content_length] + "..."

    return f"[{idx}] {icon} {role}: {content}"


def _extract_tool_call_info(tc: dict, max_args_length: int) -> tuple[str, str]:
    """
    提取工具调用的名称和参数
    """
    tc_name = tc.get("function", {}).get("name", "unknown")
    tc_args = tc.get("function", {}).get("arguments", "")

    # 尝试解析JSON参数
    try:
        args_obj = json.loads(tc_args) if tc_args else {}
        args_str = json.dumps(args_obj, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        args_str = str(tc_args)

    # 截断过长的参数
    if len(args_str) > max_args_length:
        args_str = args_str[:max_args_length] + "..."

    return tc_name, args_str
