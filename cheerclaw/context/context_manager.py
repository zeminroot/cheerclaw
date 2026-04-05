#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   context_manager.py
@Author  :   zemin
@Desc    :   上下文管理
'''

import json
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import tiktoken
from cheerclaw.utils.prompt_loader import load_prompt


_PER_MESSAGE_OVERHEAD = 4  # 每条消息的固定开销
_MIN_MESSAGE_TOKENS = 4   # 单条消息最小 token 数
_DEFAULT_ENCODING = "cl100k_base"  # tiktoken 默认编码（GPT-4/Claude 通用）


def load_memory_content(workspace: Union[str, Path]) -> str:
    """
    实时读取 MEMORY.md 文件内容
    workspace: channel workspace 路径
    返回: MEMORY.md 文件内容，文件不存在或读取失败返回提示信息
    """
    ws = Path(workspace).expanduser().resolve()
    memory_path = ws / "memory" / "MEMORY.md"

    try:
        if memory_path.exists():
            content = memory_path.read_text(encoding="utf-8")
            return content if content else "暂无长期记忆"
    except Exception:
        pass

    return "暂无长期记忆"


def estimate_prompt_tokens(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """
    估算消息列表的 Token 数量
    messages: 消息列表，每条消息是符合 OpenAI 格式的字典
    tools: 工具定义列表
    返回: 估算的 Token 数量，失败返回 0
    """
    try:
        enc = tiktoken.get_encoding(_DEFAULT_ENCODING)
        parts: List[str] = []

        for msg in messages:
            # 处理 content 字段
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content)
            # 处理 tool_calls 字段（Function Calling 的调用请求）
            tc = msg.get("tool_calls")
            if tc:
                parts.append(json.dumps(tc, ensure_ascii=False))
            # 处理 reasoning_content 字段
            rc = msg.get("reasoning_content")
            if isinstance(rc, str) and rc:
                parts.append(rc)

            # 处理 name 和 tool_call_id 字段
            for key in ("name", "tool_call_id"):
                value = msg.get(key)
                if isinstance(value, str) and value:
                    parts.append(value)

        # tools 作为 system message 的一部分给模型
        if tools:
            parts.append(json.dumps(tools, ensure_ascii=False))

        # 添加每条消息的固定开销
        per_message_overhead = len(messages) * _PER_MESSAGE_OVERHEAD
        try:
            tokens_num = len(enc.encode("\n".join(parts))) + per_message_overhead
        except Exception as e:
            tokens_num = int((len("\n".join(parts)) + per_message_overhead) / 2.5) 
            
        return tokens_num

    except Exception:
        return 0 


def estimate_message_tokens(message: Dict[str, Any]) -> int:
    content = message.get("content")
    parts: List[str] = []

    # 处理 content 字段
    if isinstance(content, str):
        parts.append(content)
    elif content is not None:
        # 非字符串内容（如 dict、list）序列化为 JSON
        parts.append(json.dumps(content, ensure_ascii=False))

    # 处理 name 和 tool_call_id 字段
    for key in ("name", "tool_call_id"):
        value = message.get(key)
        if isinstance(value, str) and value:
            parts.append(value)

    # 处理 tool_calls 字段
    if message.get("tool_calls"):
        parts.append(json.dumps(message["tool_calls"], ensure_ascii=False))

    # 处理 reasoning_content 字段
    rc = message.get("reasoning_content")
    if isinstance(rc, str) and rc:
        parts.append(rc)

    payload = "\n".join(parts)
    if not payload:
        # 空消息返回最小 token 数
        return _MIN_MESSAGE_TOKENS

    try:
        enc = tiktoken.get_encoding(_DEFAULT_ENCODING)
        return max(_MIN_MESSAGE_TOKENS, len(enc.encode(payload)) + _PER_MESSAGE_OVERHEAD)
    except Exception:
        return max(_MIN_MESSAGE_TOKENS, int(len(payload) // 2.5) + _PER_MESSAGE_OVERHEAD)


class ContextManager:

    _SAFETY_BUFFER = 1024  # 安全缓冲 token 数
    _DEFAULT_MAX_COMPLETION_TOKENS = 4096 

    def __init__(
        self,
        system_prompt_template: str = "system_prompt.md",
        context_window_tokens: int = 100000,
        max_completion_tokens: int = _DEFAULT_MAX_COMPLETION_TOKENS,
    ):
        self.system_prompt_template = system_prompt_template
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens

    def _get_workspace_paths(self, workspace: Union[str, Path]) -> tuple[Path, Path, Path]:
        """
        获取 workspace 下的各目录路径 (origin_dir, memory_dir, meta_dir)
        """
        ws = Path(workspace).expanduser().resolve()
        origin_dir = ws / "origin"
        memory_dir = ws / "memory"
        meta_dir = ws / "meta"

        origin_dir.mkdir(parents=True, exist_ok=True)
        memory_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        return origin_dir, memory_dir, meta_dir

    def _build_system_prompt(
        self, always_content, skills_summary_content, channel_id, workspace: Union[str, Path], channel_info: str = ""
    ) -> str:
        """构建系统提示词
        always_content: 常驻技能的内容描述
        skills_summary_content: 所有技能的摘要
        channel_id: 当前连接的channelid
        workspace: 当前channel的workspace路径
        返回: 构建完成的系统提示词字符串
        """
        if always_content == "":
            always_content = "暂无已加载的技能。"

        if skills_summary_content == "":
            skills_summary_content = "暂无可用skills"

        # 获取各目录路径
        origin_dir, memory_dir, meta_dir = self._get_workspace_paths(workspace)

        memory_path = memory_dir / "MEMORY.md"
        history_path = memory_dir / "HISTORY.md"

        # 获取runtime信息
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        platform_policy = ""
        if system == "Windows":
            platform_policy = """你当前运行在Windows系统，可使用Windows原生的shell命令，若终端输出内容乱码，使用UTF-8编码输出重新执行。"""
        else:
            platform_policy = """你当前运行在POSIX兼容系统，可使用标准shell工具，若终端输出内容乱码，使用UTF-8编码输出重新执行。"""

        # memory_content 不再在这里读取，调用处实时读取
        return load_prompt(
            "system_prompt.md",
            skills_summary=skills_summary_content,
            always_skills=always_content,
            clawspace=str(Path.home() / ".cheerclaw"),
            workspace=str(workspace),
            memory_path=str(memory_path),
            history_path=str(history_path),
            runtime=runtime,
            platform_policy=platform_policy,
            channel_id=channel_id,
            channel_info=channel_info,
            memory_content="{memory_content}",  
        )

    def load_history(self, workspace: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        加载指定 workspace 的对话历史
        文件不存在或损坏时返回空列表
        """
        origin_dir, _, _ = self._get_workspace_paths(workspace)
        jsonl_file = origin_dir / "origin_qas.jsonl"

        if not jsonl_file.exists():
            return []

        messages: List[Dict[str, Any]] = []

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        return messages

    def save_history(self, workspace: Union[str, Path], messages: List[Dict[str, Any]]):
        origin_dir, _, _ = self._get_workspace_paths(workspace)
        jsonl_file = origin_dir / "origin_qas.jsonl"

        with open(jsonl_file, "w", encoding="utf-8") as f:
            for msg in messages:
                try:
                    json_line = json.dumps(msg, ensure_ascii=False)
                    f.write(json_line + "\n")
                except Exception:
                    continue

    def append_to_history(self, channel_id: str, message: Dict[str, Any]):
        jsonl_file = self._history_dir / f"{channel_id}.jsonl"

        with open(jsonl_file, "a", encoding="utf-8") as f:
            json_line = json.dumps(message, ensure_ascii=False)
            f.write(json_line + "\n")

    def load_meta(self, workspace: Union[str, Path]) -> Dict[str, Any]:
        _, _, meta_dir = self._get_workspace_paths(workspace)
        json_file = meta_dir / "meta.json"

        if not json_file.exists():
            return {}

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_meta(self, workspace: Union[str, Path], meta: Dict[str, Any]):
        _, _, meta_dir = self._get_workspace_paths(workspace)
        json_file = meta_dir / "meta.json"

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def get_safe_context_budget(self) -> int:
        return self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER

    def calculate_compress_point(
        self,
        messages: List[Dict[str, Any]],
        current_compress_idx: int,
        tokens_to_remove: int,
    ) -> int:
        """计算新的压缩点索引
        messages: 完整对话历史消息列表
        current_compress_idx: 当前压缩点索引
        tokens_to_remove: 需要移除的 token 数量
        返回: 新的压缩点索引，如果不需要移除或输入无效则返回 current_compress_idx
        """
        if tokens_to_remove <= 0:
            return current_compress_idx

        if current_compress_idx >= len(messages):
            return current_compress_idx

        removed_tokens = 0
        new_compress_idx = current_compress_idx

        for idx in range(current_compress_idx, len(messages)):
            msg = messages[idx]
            msg_tokens = estimate_message_tokens(msg)
            removed_tokens += msg_tokens

            # 在用户消息处标记压缩点
            if msg.get("role") == "user" and removed_tokens >= tokens_to_remove:
                new_compress_idx = idx
                break

        if new_compress_idx == current_compress_idx:
            remaining = len(messages) - current_compress_idx
            if remaining > 2:
                new_compress_idx = current_compress_idx + remaining // 2

        return new_compress_idx

    def get_context_stats(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """获取上下文统计信息
        messages: 消息列表
        max_tokens: 上下文窗口限制
        tools: 工具定义列表
        返回: 统计信息字典，包含 message_count/total_tokens/max_tokens/safe_budget/usage_ratio/safe_usage_ratio/role_counts/token_breakdown/needs_truncation
        """
        if max_tokens is None:
            max_tokens = self.context_window_tokens

        total_tokens = estimate_prompt_tokens(messages, tools)

        role_counts: Dict[str, int] = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        token_breakdown: Dict[str, int] = {}
        # for msg in messages:
        #     role = msg.get("role", "unknown")
        #     msg_tokens = estimate_message_tokens(msg)
        #     token_breakdown[role] = token_breakdown.get(role, 0) + msg_tokens

        safe_budget = self.get_safe_context_budget()

        return {
            "message_count": len(messages),
            "total_tokens": total_tokens,
            "max_tokens": max_tokens,
            "safe_budget": safe_budget,
            "usage_ratio": total_tokens / max_tokens if max_tokens > 0 else 0,
            "safe_usage_ratio": total_tokens / safe_budget if safe_budget > 0 else 0,
            "role_counts": role_counts,
            "token_breakdown": token_breakdown,
            "needs_truncation": total_tokens > safe_budget,
        }
