#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   llm_client.py
@Author  :   zemin
@Desc    :   LLM客户端
'''

import json
from typing import TYPE_CHECKING, Any, Optional
from loguru import logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI


def _get_thinking_kwargs(model: str, enable: bool) -> dict:
    """根据模型名称获取思考模式参数
    model: 模型名称
    enable: 是否启用思考模式 (True=启用, False=禁用)
    返回: 需要合并到 api_kwargs 的字典
    """
    model_lower = model.lower()

    if "kimi" in model_lower:
        # 默认开启，enable=False 时禁用
        if not enable:
            return {"thinking": {"type": "disabled"}}
        # enable=True 时 kimi 默认就是思考模式，无需额外参数
        return {}
    elif "qwen" in model_lower:
        return {"extra_body": {"enable_thinking": enable}}

    return {}


async def call_llm(
    client: "AsyncOpenAI",
    model: str,
    messages: list[dict],
    tools: Optional[list] = None,
) -> dict:
    """调用 LLM API 思考模式
    client: OpenAI 异步客户端
    model: 模型名称
    messages: 消息列表
    tools: 工具定义列表（可选）
    返回: 包含 content 和 tool_calls 的字典 
    tool_calls: 工具调用列表，每项包含 id, name, arguments
    """
    try:
        api_kwargs = {"model": model, "messages": messages}
        if tools:
            api_kwargs["tools"] = tools
            api_kwargs["tool_choice"] = "auto"

        api_kwargs.update(_get_thinking_kwargs(model, enable=True))

        completion = await client.chat.completions.create(**api_kwargs)

        message = completion.choices[0].message

        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                {"id": tc.id, "name": tc.function.name, "arguments": json.loads(tc.function.arguments)}
                for tc in message.tool_calls
            ]

        # 提取推理内容
        reasoning_content = getattr(message, "reasoning_content", None)

        # 构建完整的 response
        response = {
            "content": message.content,
            "tool_calls": tool_calls,
            "reasoning_content": reasoning_content,
        }
        return response
    except Exception as e:
        return {"content": f"调用 LLM 出错: {str(e)}", "tool_calls": None}


async def call_llm_with_forced_tool(
    client: "AsyncOpenAI",
    model: str,
    messages: list[dict],
    tools: list,
    tool_name: str,
    temperature: float = 0.3,
) -> dict[str, Any] | None:
    """调用 LLM API 并强制使用指定工具
    client: OpenAI 异步客户端
    model: 模型名称
    messages: 消息列表
    tools: 工具定义列表
    tool_name: 强制使用的工具名称
    temperature: 温度参数，默认 0.3 确保输出稳定
    返回: 包含 name 和 arguments 的字典，或 None 表示失败
    """
    try:
        api_kwargs = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
            "temperature": temperature,
        }

        # call_llm_with_forced_tool 禁用思考模式
        api_kwargs.update(_get_thinking_kwargs(model, enable=False))

        response = await client.chat.completions.create(**api_kwargs)

        message = response.choices[0].message

        # 检查工具调用
        if not message.tool_calls:
            logger.error(f"[call_llm_with_forced_tool] 失败: 没有工具调用，message={message}")
            return None

        # 解析工具调用
        tool_call = message.tool_calls[0]
        if tool_call.function.name != tool_name:
            logger.error(f"[call_llm_with_forced_tool] 失败: 工具名不匹配，期望={tool_name}，实际={tool_call.function.name}")
            return None

        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            logger.error(f"[call_llm_with_forced_tool] 失败: JSON解析错误，args={tool_call.function.arguments}，error={e}")
            return None

        return {
            "name": tool_call.function.name,
            "arguments": arguments,
        }

    except Exception as e:
        logger.error(f"[call_llm_with_forced_tool] 失败: 异常={e}")
        return None


__all__ = [
    "call_llm",
    "call_llm_with_forced_tool",
]

