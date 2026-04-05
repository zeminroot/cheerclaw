#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   agent_helpers.py
@Author  :   zemin
@Desc    :   Agent 辅助函数
'''

from typing import TYPE_CHECKING

from cheerclaw.utils.llm_client import call_llm
from cheerclaw.show_style.diff_helper import format_diff

if TYPE_CHECKING:
    from openai import AsyncOpenAI


def format_tool_confirm_message(tool_name: str, arguments: dict, reason: str, agent_tag: str = "") -> str:
    """
    格式化工具确认消息
    tool_name: 工具名称
    arguments: 工具参数
    reason: 确认原因
    agent_tag: Agent标识
    返回:格式化后的确认消息
    """
    if agent_tag:
        base_msg = f"⏸️ [{agent_tag}需要确认]\n原因: {reason}\n工具: {tool_name}\n"
    else:
        base_msg = f"⏸️ 需要确认: {reason}\n工具名: {tool_name}\n"

    if tool_name == "edit_file":
        path = arguments.get("path", "")
        old_string = arguments.get("old_string", "")
        new_string = arguments.get("new_string", "")
        diff_str = format_diff(old_string, new_string)
        return base_msg + f"\n文件: {path}\n差异对比:\n```diff\n{diff_str}\n```\n\n请输入:\n「是」确认执行\n输入其他内容跳过"

    elif tool_name == "write_file":
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        diff_str = format_diff("", content)
        return base_msg + f"\n文件: {path}\n差异对比:\n```diff\n{diff_str}\n```\n\n请输入:\n「是」确认执行\n输入其他内容跳过"

    else:
        return base_msg + "\n请输入:\n「是」确认执行\n输入其他内容跳过"


def check_tool_needs_confirm(
    tool_name: str,
    arguments: dict,
    config,
) -> tuple[bool, str]:
    """检查工具是否需要确认
    tool_name: 工具名称
    arguments: 工具参数
    config: 配置对象
    返回: (是否需要确认, 原因)
    """
    confirm_tools = set(config.agent.confirm_tools)
    dangerous_keywords = set(config.agent.dangerous_keywords)

    # manage_cron_task 工具不需要确认
    if tool_name in ("manage_cron_task"):
        return False, ""

    # 检查文件操作路径是否在 .cheerclaw 目录下（系统目录，无需确认）
    if tool_name in ("write_file", "edit_file"):
        path = arguments.get("path", "")
        if path and ".cheerclaw" in path.replace("\\", "/"):
            return False, ""

    # 检查是否在需要确认的工具列表中
    if tool_name in confirm_tools:
        return True, f"这是一个文件修改操作（{tool_name}）"

    # 检查 shell 命令中的危险关键字
    if tool_name == "exec":
        command = arguments.get("command", "").lower()
        # 检查是否是针对 .cheerclaw/cron 目录的操作（系统操作，无需确认）
        if ".cheerclaw/cron" in command.replace("\\", "/"):
            return False, ""
        # 检查危险关键字
        for keyword in dangerous_keywords:
            if keyword in command:
                return True, f"Shell 命令包含危险关键字：{keyword}"

    return False, ""


async def generate_summary_from_tools(
    messages: list,
    client: "AsyncOpenAI",
    model: str,
) -> str:
    """基于工具调用结果生成任务总结
    当达到最大迭代次数时使用
    messages: 对话历史消息列表
    client: OpenAI 客户端
    model: 模型名称
    返回: 生成的总结字符串
    """
    summary_prompt = """你已达到最大工具调用次数限制。请基于当前任务下已执行的工具调用结果，生成一个简洁的回答。直接输出回答内容，不要调用任何工具。"""

    summary_messages = messages + [{"role": "user", "content": summary_prompt}]

    try:
        response = await call_llm(
            client=client,
            model=model,
            messages=summary_messages,
            tools=None,
        )

        summary = response.get("content", "")
        if summary:
            return f"{summary}"
    except Exception:
        pass

    return f"(达到最大迭代次数仍未输出结果强制停止)"
