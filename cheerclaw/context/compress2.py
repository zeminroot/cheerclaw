#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   compress2.py
@Author  :   zemin
@Desc    :   
双层记忆系统 使用幽灵工具 强制工具调用但不执行
提供对话上下文的双层记忆功能：
1. 长期记忆（MEMORY.md）：存储精简的重要事实、用户偏好、关键信息
2. 历史日志（HISTORY.md）：按时间顺序记录事件摘要，支持grep搜索
'''

from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from loguru import logger
from cheerclaw.utils.llm_client import call_llm_with_forced_tool
from cheerclaw.utils.openai_client import create_openai_client
if TYPE_CHECKING:
    from openai import AsyncOpenAI


# save_memory 工具
_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "将记忆整合结果保存到持久化存储中。",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": (
                            "一段总结关键事件/决策/主题的段落。"
                            "以 [YYYY-MM-DD HH:MM] 格式开头，时间戳从对话消息的前缀中提取（消息格式如：[2026-04-05 17:48] 用户发起...）。"
                            "包含对grep搜索有用的细节。"
                        ),
                    },
                    "memory_update": {
                        "type": "string",
                        "description": (
                            "以Markdown格式呈现的完整更新后的长期记忆。需包含原有+新增用户偏好/个人画像等事实信息。"
                            "长期记忆内容十分简要，禁止将`定时任务`当做长期记忆。若无新内容则返回原内容不变。"
                        ),
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


def _ensure_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _normalize_tool_args(args: Any) -> dict[str, Any] | None:
    if isinstance(args, str):
        args = json.loads(args)
    if isinstance(args, list):
        return args[0] if args and isinstance(args[0], dict) else None
    return args if isinstance(args, dict) else None


def _format_messages_for_prompt(messages: list[dict[str, Any]]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if not content and role != "assistant":
            continue

        ts = msg.get("timestamp", "")[:16] if msg.get("timestamp") else "?"

        # 处理工具调用
        if role == "assistant" and msg.get("tool_calls"):
            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in msg["tool_calls"]]
            tool_info = f" [工具: {', '.join(tool_names)}]"
            lines.append(f"[{ts}] ASSISTANT{tool_info}: {content[:500] if content else '[调用工具]'}")
        # 处理工具结果
        elif role == "tool":
            tool_name = msg.get("name", "unknown")
            content_str = str(content)[:300] if content else ""
            lines.append(f"[{ts}] TOOL ({tool_name}): {content_str}{'...' if len(str(content)) > 300 else ''}")
        else:
            content_str = str(content)[:10000] if content else ""
            lines.append(f"[{ts}] {role.upper()}: {content_str}{'...' if len(str(content)) > 10000 else ''}")

    return "\n".join(lines)


class LLMContextCompressor:

    _MAX_FAILURES_BEFORE_FALLBACK = 3

    def __init__(
        self,
        client: Optional[AsyncOpenAI] = None,
        model: Optional[str] = None,
    ):
        self.model = model or "gpt-3.5-turbo"

        if client:
            self.client = client
        else:
            try:
                self.client = create_openai_client()
            except Exception:
                self.client = None

    def _get_memory_dir(self, channel_workspace: Path) -> Path:
        memory_dir = channel_workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        return memory_dir

    def _get_history_file(self, channel_workspace: Path) -> Path:
        return self._get_memory_dir(channel_workspace) / "HISTORY.md"

    def _get_memory_file(self, channel_workspace: Path) -> Path:
        return self._get_memory_dir(channel_workspace) / "MEMORY.md"

    def _read_memory(self, channel_workspace: Path) -> str:
        memory_file = self._get_memory_file(channel_workspace)
        if memory_file.exists():
            return memory_file.read_text(encoding="utf-8")
        return ""

    def _write_memory(self, channel_workspace: Path, content: str) -> None:
        memory_file = self._get_memory_file(channel_workspace)
        memory_file.write_text(content, encoding="utf-8")

    def _append_to_history(self, channel_workspace: Path, entry: str) -> None:
        history_file = self._get_history_file(channel_workspace)
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    async def compress_from_point(
        self,
        channel_workspace: Path,
        local_history: list[dict],
        last_compress_idx: int,
        new_compress_idx: int,
    ) -> str:
        """
        压缩两个压缩点之间的消息，整合到双层记忆文件中
        channel_workspace: 当前 channel 的 workspace 路径
        local_history: 完整的对话历史
        last_compress_idx: 上一个压缩点
        new_compress_idx: 新的压缩点
        返回: 保存到HISTORY.md的历史条目内容
        """
        if last_compress_idx >= new_compress_idx:
            return ""

        # 提取要压缩的消息
        messages_to_compress = local_history[last_compress_idx:new_compress_idx]
        if not messages_to_compress:
            return ""

        # 使用LLM进行记忆整合
        result = await self._consolidate_memory(
            channel_workspace=channel_workspace,
            messages=messages_to_compress,
            start_idx=last_compress_idx,
            end_idx=new_compress_idx,
        )

        return result

    async def _consolidate_memory(
        self,
        channel_workspace: Path,
        messages: list[dict[str, Any]],
        start_idx: int,
        end_idx: int,
    ) -> str:
        """
        使用大模型进行记忆压缩
        返回: 写入HISTORY.md的历史条目
        """
        if not self.client:
            logger.warning("LLM 客户端未配置，使用原始归档")
            return self._raw_archive(channel_workspace, messages, start_idx, end_idx)

        # 读取当前长期记忆
        current_memory = self._read_memory(channel_workspace)

        # 构建提示词
        formatted_messages = _format_messages_for_prompt(messages)
        system_prompt = """
        你是一名记忆整合助手。调用save_memory工具完成记忆整合。"""

        user_prompt = f"""处理这段对话并调用save_memory工具完成记忆整合。
        ## 当前长期记忆
        {current_memory or "(空)"}
        ## 待处理的对话
        {formatted_messages}"""

        try:
            # 调用LLM
            result = await self._call_llm_with_retry(system_prompt, user_prompt)

            if result is None:
                logger.warning("记忆整合失败，使用原始归档")
                return self._raw_archive(channel_workspace, messages, start_idx, end_idx)

            # 解析工具调用结果
            args = _normalize_tool_args(result.get("arguments", {}))
            if args is None:
                logger.warning("工具调用参数解析失败，使用原始归档")
                return self._raw_archive(channel_workspace, messages, start_idx, end_idx)

            history_entry = _ensure_text(args.get("history_entry", "")).strip()
            memory_update = args.get("memory_update", "")

            if not history_entry:
                logger.warning("历史条目为空，使用原始归档")
                return self._raw_archive(channel_workspace, messages, start_idx, end_idx)

            # 写入HISTORY.md
            self._append_to_history(channel_workspace, history_entry)

            # 写入MEMORY.md
            if memory_update:
                memory_update = _ensure_text(memory_update)
                if memory_update != current_memory:
                    self._write_memory(channel_workspace, memory_update)

            logger.info(f"记忆整合完成：处理了 {len(messages)} 条消息")
            return history_entry

        except Exception as e:
            logger.exception(f"记忆整合异常: {e}")
            return self._raw_archive(channel_workspace, messages, start_idx, end_idx)

    async def _call_llm_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any] | None:
        """
        调用大模型
        返回: 包含 name 和 arguments 的字典，None 表示失败
        """
        if not self.client:
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 最多重试3次
        for attempt in range(self._MAX_FAILURES_BEFORE_FALLBACK):
            try:
                result = await call_llm_with_forced_tool(
                    client=self.client,
                    model=self.model,
                    messages=messages,
                    tools=_SAVE_MEMORY_TOOL,
                    tool_name="save_memory",
                    temperature=0.3,
                )

                if result is not None:
                    return result

                logger.warning(f"记忆整合调用失败，第 {attempt + 1} 次重试")

            except Exception as e:
                logger.warning(f"记忆整合调用异常: {e}，第 {attempt + 1} 次重试")

        return None

    def _raw_archive(
        self,
        channel_workspace: Path,
        messages: list[dict[str, Any]],
        start_idx: int,
        end_idx: int,
    ) -> str:
        """
        原始归档：将消息直接写入HISTORY.md，不调用LLM MEMORY.md保持不变
        channel_workspace: channel 的 workspace 路径
        messages: 要归档的消息列表
        start_idx: 起始索引
        end_idx: 结束索引
        返回: 写入的历史条目
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 格式化原始消息
        lines = [
            f"[{timestamp}] [RAW] {len(messages)} 条消息（索引 {start_idx}:{end_idx}）",
            "",
        ]

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")[:16] if msg.get("timestamp") else timestamp

            if role == "assistant" and msg.get("tool_calls"):
                tool_names = [tc.get("function", {}).get("name", "unknown") for tc in msg["tool_calls"]]
                lines.append(f"[{ts}] ASSISTANT [工具: {', '.join(tool_names)}]: {content[:200] if content else '[调用工具]'}")
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                lines.append(f"[{ts}] TOOL ({tool_name}): {str(content)[:150]}")
            else:
                lines.append(f"[{ts}] {role.upper()}: {str(content)[:1000]}")

        entry = "\n".join(lines)

        # 追加到HISTORY.md
        self._append_to_history(channel_workspace, entry)

        logger.warning(f"记忆整合降级：原始归档了 {len(messages)} 条消息")
        return entry

    def read_history(self, channel_workspace: Path) -> str:
        history_file = self._get_history_file(channel_workspace)
        if not history_file.exists():
            return ""
        return history_file.read_text(encoding="utf-8")

    def read_memory(self, channel_workspace: Path) -> str:
        return self._read_memory(channel_workspace)

    def clear_compressed_history(self, channel_workspace: Path) -> None:
        """
        清空指定channel的记忆 channel_workspace: channel 的 workspace 路径
        """
        # 清空 HISTORY.md
        history_file = self._get_history_file(channel_workspace)
        if history_file.exists():
            history_file.write_text("", encoding="utf-8")
            logger.info(f"已清空历史日志: {history_file}")

        # 清空 MEMORY.md
        memory_file = self._get_memory_file(channel_workspace)
        if memory_file.exists():
            memory_file.write_text("", encoding="utf-8")
            logger.info(f"已清空长期记忆: {memory_file}")


