#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   sub_agent.py
@Author  :   zemin
@Desc    :   子agent
'''

import asyncio
import json
import platform
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from cheerclaw.tools_module import ToolRegistry, ToolResult
from cheerclaw.tools_module.base import Tool
from cheerclaw.tools_module.calculator import CalculatorTool
from cheerclaw.tools_module.filesystem import ReadFileTool, WriteFileTool, ListDirTool, EditFileTool
from cheerclaw.tools_module.shell import ExecTool
from cheerclaw.tools_module.read_skill import ReadSkillTool
from cheerclaw.tools_module.tavily_search import TavilySearchTool
from cheerclaw.utils.llm_client import call_llm
from cheerclaw.utils.prompt_loader import load_prompt
from cheerclaw.utils.agent_helpers import generate_summary_from_tools, format_tool_confirm_message, check_tool_needs_confirm


TOOL_CLASS_MAP = {
    "calculate": CalculatorTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "list_dir": ListDirTool,
    "edit_file": EditFileTool,
    "exec": ExecTool,
    "read_skill": ReadSkillTool,
    "tavily_search": TavilySearchTool,
}


class SubAgent:

    def __init__(
        self,
        config,
        tools_schemas: list[dict],
        skill_loader,
        always_content: str,
        model: str,
        client: "AsyncOpenAI",
        max_iterations: int = 20,
    ):
        self.config = config
        # tools_schemas 由 use_subagent_tool 过滤
        self.tools_schemas = tools_schemas
        self.skill_loader = skill_loader
        self.always_content = always_content
        self.model = model
        self.client = client
        self.max_iterations = max_iterations

        # 创建独立的工具注册表
        self.tool_registry = self._create_tool_registry()

    def _create_tool_registry(self) -> ToolRegistry:
        """
        创建子Agent的工具注册表 根据传入的tools_schemas动态创建工具实例
        """
        registry = ToolRegistry()

        for schema in self.tools_schemas:
            tool_name = schema["function"]["name"]
            tool_class = TOOL_CLASS_MAP.get(tool_name)

            if tool_class:
                if tool_name == "read_skill":
                    registry.register(tool_class(self.skill_loader))
                else:
                    registry.register(tool_class())

        return registry

    async def run(
        self,
        task_description: str,
        channel_id: str,
        input_q: asyncio.Queue,
        output_q: asyncio.Queue,
        channel_workspace: Path,
    ) -> str:
        """
        运行子Agent执行任务
        task_description: 完整独立的任务描述
        channel_id: channel标识(与主Agent一致)
        input_q: 输入队列(与主Agent共享)
        output_q: 输出队列(与主Agent共享)
        channel_workspace: workspace路径(与主Agent一致)
        返回: 执行结果字符串
        """
        system_prompt = self._build_system_prompt(
            channel_id=channel_id,
            channel_workspace=channel_workspace,
        )

        messages: list[dict] = []
        messages.append({"role": "user", "content": task_description})
        await output_q.put((channel_id, "🔄 [子Agent] 开始执行任务..."))

        # ReAct循环
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            llm_messages = [{"role": "system", "content": system_prompt}] + messages
            response = await call_llm(
                client=self.client,
                model=self.model,
                messages=llm_messages,
                tools=self.tools_schemas,
            )

            if response.get("reasoning_content"):
                await output_q.put((channel_id, f"💭 [子Agent思考] {response['reasoning_content']}"))
                logger.debug(f"[子Agent思考过程] {response['reasoning_content']}")

            # 检查工具调用
            if response.get("tool_calls"):
                tool_calls = response["tool_calls"]

                # 添加assistant消息到历史
                assistant_msg = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"])
                            }
                        }
                        for tc in tool_calls
                    ]
                }
                messages.append(assistant_msg)

                # 执行工具(带确认机制)
                await self._execute_tools_with_confirmation(
                    tool_calls=tool_calls,
                    messages=messages,
                    channel_id=channel_id,
                    input_q=input_q,
                    output_q=output_q,
                )
                continue
            else:
                # 无工具调用，得到最终回复
                final_reply = response.get("content", "(无回复)")
                messages.append({"role": "assistant", "content": final_reply})
                await output_q.put((channel_id, "✅ [子Agent] 任务完成"))
                return final_reply

        # 达到最大迭代次数，基于工具调用结果生成总结
        await output_q.put((channel_id, "🔄 [子Agent] 达到最大迭代次数，正在生成任务总结..."))
        return await generate_summary_from_tools(
            messages=messages,
            client=self.client,
            model=self.model,
        )

    async def _execute_tools_with_confirmation(
        self,
        tool_calls: list,
        messages: list,
        channel_id: str,
        input_q: asyncio.Queue,
        output_q: asyncio.Queue,
    ) -> None:
        """
        执行工具调用，对需要确认的工具向用户请求确认
        tool_calls: 工具调用列表
        messages: 对话历史(会被修改添加工具结果)
        channel_id: channel标识
        input_q: 输入队列
        output_q: 输出队列
        """
        # 分离需要确认和不需要确认的工具
        no_confirm_tools = []
        need_confirm_tools = []

        for tc in tool_calls:
            needs_confirm, reason = check_tool_needs_confirm(tc["name"], tc["arguments"], self.config)
            if needs_confirm:
                need_confirm_tools.append((tc, reason))
            else:
                no_confirm_tools.append(tc)

        # 执行不需要确认的工具
        for tc in no_confirm_tools:
            tool_name = tc["name"]
            arguments = tc["arguments"]
            await output_q.put((channel_id, f"🔧 [子Agent] 执行: {tool_name}"))
            logger.debug(f"[子Agent工具执行] 工具名: {tool_name}, 参数: {arguments}")

            # 执行工具
            result = await self.tool_registry.execute(tool_name, arguments)

            if result.success:
                await output_q.put((channel_id, f"✓ [子Agent] {tool_name} 成功"))
                logger.debug(f"[子Agent工具结果] 工具名: {tool_name}, 结果: {str(result.data)[:200]}")
            else:
                await output_q.put((channel_id, f"✗ [子Agent] {tool_name} 失败"))
                logger.debug(f"[子Agent工具结果] 工具名: {tool_name}, 错误: {str(result.error)[:200]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tool_name,
                "content": str(result.data if result.success else result.error),
            })

        # 处理需要确认的工具
        for tc, reason in need_confirm_tools:
            tool_name = tc["name"]
            arguments = tc["arguments"]
            logger.debug(f"[子Agent工具执行-需确认] 工具名: {tool_name}, 参数: {arguments}")

            confirm_msg = self._format_tool_confirm_message(tool_name, arguments, reason)
            await output_q.put((channel_id, confirm_msg))

            # 等待用户回复(从共享队列获取)
            user_reply = await input_q.get()
            if user_reply and user_reply.strip() == "是":
                # 执行工具
                result = await self.tool_registry.execute(tool_name, arguments)
                status = "成功" if result.success else "失败"
                await output_q.put((channel_id, f"[子Agent] {tool_name} {status}"))
                if result.success:
                    logger.debug(f"[子Agent工具结果-需确认] 工具名: {tool_name}, 结果: {str(result.data)[:200]}")
                else:
                    logger.debug(f"[子Agent工具结果-需确认] 工具名: {tool_name}, 错误: {str(result.error)[:200]}")
            else:
                # 构建详细的取消消息，包含用户的回复内容
                user_response = user_reply.strip() if user_reply else "（无回复/超时）"
                cancel_msg = f"工具 {tool_name} 执行被取消。原因：用户未确认执行。用户回复：「{user_response}」"
                result = ToolResult(tool_name=tool_name, success=True, data=cancel_msg)
                await output_q.put((channel_id, f"[子Agent] {tool_name} 取消"))
                logger.debug(f"[子Agent工具结果-需确认] 工具名: {tool_name}, 状态: 用户取消")

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tool_name,
                "content": str(result.data if result.success else result.error),
            })

    def _format_tool_confirm_message(self, tool_name: str, arguments: dict, reason: str) -> str:
        """
        格式化子Agent确认消息
        """
        return format_tool_confirm_message(tool_name, arguments, reason, agent_tag="子Agent")

    def _build_system_prompt(
        self,
        channel_id: str,
        channel_workspace: Path,
    ) -> str:
        """
        构建子Agent的系统提示词
        channel_id: channel标识
        channel_workspace: workspace路径
        返回: 系统提示词字符串
        """
        skills_summary = self.skill_loader.build_skills_summary()
        always_skills = self.always_content if self.always_content else "暂无已加载的技能。"

        if skills_summary == "":
            skills_summary = "暂无可用skills"

        # 获取各目录路径
        clawspace = Path.home() / ".cheerclaw"
        memory_path = channel_workspace / "memory" / "MEMORY.md"
        history_path = channel_workspace / "memory" / "HISTORY.md"

        # 获取runtime信息
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        platform_policy = ""
        if system == "Windows":
            platform_policy = """你当前运行在Windows系统，可使用Windows原生的shell命令，若终端输出内容乱码，使用UTF-8编码输出重新执行。"""
        else:
            platform_policy = """你当前运行在POSIX兼容系统，可使用标准shell工具，若终端输出内容乱码，使用UTF-8编码输出重新执行。"""

        # 读取长期记忆
        memory_content = ""
        try:
            if memory_path.exists():
                memory_content = memory_path.read_text(encoding="utf-8")
        except Exception:
            memory_content = "（读取记忆文件失败）"

        if not memory_content:
            memory_content = "暂无长期记忆"

        return load_prompt(
            "sub_agent_prompt.md",
            skills_summary=skills_summary,
            always_skills=always_skills,
            clawspace=str(clawspace),
            workspace=str(channel_workspace),
            memory_path=str(memory_path),
            history_path=str(history_path),
            runtime=runtime,
            platform_policy=platform_policy,
            channel_id=channel_id,
            memory_content=memory_content,
        )
