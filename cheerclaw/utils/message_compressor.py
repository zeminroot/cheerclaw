#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   message_compressor.py
@Author  :   zemin
@Desc    :   消息压缩工具：对工具调用相关的消息进行截断压缩
'''


def identify_conversation_boundaries(messages: list[dict]) -> list[int]:
    """
    识别对话边界，返回每个对话起始消息的索引
    一次对话 = user消息 + 其后的所有消息直到下一个user消息

    Args:
        messages: 消息列表

    Returns:
        每个对话起始消息的索引列表，如 [0, 5, 10] 表示第0、5、10条消息是新对话的开始
    """
    boundaries = []
    i = 0
    while i < len(messages):
        if messages[i].get("role") == "user":
            boundaries.append(i)
            # 跳过这轮对话的所有消息（包括assistant的工具调用和tool结果）
            i += 1
            while i < len(messages) and messages[i].get("role") != "user":
                i += 1
        else:
            i += 1
    return boundaries


def compress_tools_in_message(msg: dict, max_len: int = 50) -> dict:
    """
    对单条消息进行工具压缩：
    - assistant + tool_calls: 替换 arguments 为压缩标记（保持JSON合法）
    - tool: 截断 content 到 max_len 字
    - 其他: 保持不变

    Args:
        msg: 原始消息字典
        max_len: 截断长度，默认50字符

    Returns:
        压缩后的消息字典（浅拷贝，不修改原始消息）
    """
    msg_copy = dict(msg)

    if msg_copy.get("role") == "assistant" and msg_copy.get("tool_calls"):
        tool_calls = []
        for tc in msg_copy["tool_calls"]:
            tc_copy = dict(tc)
            if "function" in tc_copy:
                func_copy = dict(tc_copy["function"])
                args = func_copy.get("arguments", "")
                # 保持JSON格式合法且为对象格式，替换为压缩标记对象
                if isinstance(args, str) and len(args) > max_len:
                    func_copy["arguments"] = '{"_compressed_":true,"note":"content truncated"}'
                tc_copy["function"] = func_copy
            tool_calls.append(tc_copy)
        msg_copy["tool_calls"] = tool_calls

    elif msg_copy.get("role") == "tool":
        content = msg_copy.get("content", "")
        if isinstance(content, str) and len(content) > max_len:
            msg_copy["content"] = content[:max_len] + "..."

    return msg_copy


def prepare_messages_for_llm(messages: list[dict], keep_recent_rounds: int = 3, max_len: int = 50) -> list[dict]:
    """
    准备发送给LLM的消息：
    1. 保留最近 N 轮对话的完整内容
    2. 对更早的消息进行工具压缩

    Args:
        messages: 原始消息列表
        keep_recent_rounds: 保留最近几轮对话的完整内容，默认3轮
        max_len: 工具内容截断长度，默认50字符

    Returns:
        处理后的消息列表（浅拷贝，不修改原始消息列表中的字典）
    """
    if not messages:
        return []

    boundaries = identify_conversation_boundaries(messages)

    if len(boundaries) <= keep_recent_rounds:
        return list(messages)

    keep_from_idx = boundaries[-keep_recent_rounds]

    processed = []
    for i, msg in enumerate(messages):
        if i < keep_from_idx:
            processed.append(compress_tools_in_message(msg, max_len))
        else:
            processed.append(msg)

    return processed
