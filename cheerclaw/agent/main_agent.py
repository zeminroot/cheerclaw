#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   main_agent.py
@Author  :   zemin
@Desc    :   主Agent
'''

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import asyncio
from loguru import logger
from cheerclaw.config.config_loader import load_config
from cheerclaw.config.config_schema import Config
from cheerclaw.tools_module.filesystem import ReadFileTool, WriteFileTool, ListDirTool, EditFileTool
from cheerclaw.tools_module.calculator import CalculatorTool
from cheerclaw.tools_module.shell import ExecTool
from cheerclaw.tools_module.read_skill import ReadSkillTool
from cheerclaw.tools_module.tavily_search import TavilySearchTool
from cheerclaw.tools_module.todo_list import TodoListManager, UpdateTodoTool
from cheerclaw.tools_module.send_message import SendMessageTool
from cheerclaw.tools_module.cron_task import ManageCronTaskTool, CronTaskManager
from cheerclaw.tools_module import ToolRegistry, ToolResult
from cheerclaw.utils.channel_info import ChannelInfoManager
from cheerclaw.agent.use_subagent_tool import UseSubagentTool
from cheerclaw.skills_module import SkillLoader
from cheerclaw.utils.history_formatter import format_history_for_display
from cheerclaw.utils.llm_client import call_llm
from cheerclaw.utils.openai_client import create_openai_client
from cheerclaw.utils.agent_helpers import generate_summary_from_tools, format_tool_confirm_message, check_tool_needs_confirm
from cheerclaw.context.context_manager import ContextManager, load_memory_content
from cheerclaw.context.compress2 import LLMContextCompressor

class AgentApp:

    def __init__(self, config: Optional[Config] = None, runspace: Path | str | None = None, channel_info_manager: Optional[ChannelInfoManager] = None):
        """初始化 AgentApp
        config: 配置对象
        runspace: 运行路径（程序启动时的当前工作目录）
        channel_info_manager: Channel 信息管理器
        """
        self.runspace = Path(runspace) if runspace else Path.cwd()
        self.config = config or load_config()
        self.channel_info_manager = channel_info_manager

        provider_cfg = self.config.provider
        self.api_key = provider_cfg.api_key
        self.api_base = provider_cfg.api_base
        self.model = provider_cfg.model
        self.timeout = provider_cfg.timeout
        self.model_max_context = getattr(provider_cfg, 'max_context', 100000)
        self.max_completion_tokens = getattr(provider_cfg, 'max_completion_tokens', 4096)
        self.compress_threshold = self.model_max_context - self.max_completion_tokens - 1024
        agent_cfg = self.config.agent
        self.agent_name = agent_cfg.name
        # 初始化 OpenAI 客户端
        if self.api_key and self.api_base and self.model:
            self.client = create_openai_client(self.config)
        else:
            self.client = None

        self.skill_loader = SkillLoader()
        self.skills_summary = self.skill_loader.build_skills_summary()
        self.always_content = self.skill_loader.get_always_skills_content()

        self.todo_manager = TodoListManager()
        clawspace = Path.home() / ".cheerclaw"
        self.cron_task_manager = CronTaskManager(clawspace=clawspace)
        self.tool_registry = ToolRegistry()

        self.tool_registry.register_many([
            CalculatorTool(),
            ReadFileTool(),
            WriteFileTool(),
            ListDirTool(),
            EditFileTool(),
            ExecTool(),
            ReadSkillTool(self.skill_loader),
            UpdateTodoTool(self.todo_manager),
            SendMessageTool(self.channel_info_manager),
            ManageCronTaskTool(self.cron_task_manager),
            TavilySearchTool(),
        ])

        base_tools_schemas = self.tool_registry.get_schemas()

        if self.client:
            use_subagent_tool = UseSubagentTool(
                config=self.config,
                skill_loader=self.skill_loader,
                tools_schemas=base_tools_schemas,
                model=self.model,
                client=self.client,
            )
            self.tool_registry.register(use_subagent_tool)

        # 更新最终tools_schemas
        self._tools_schemas = self.tool_registry.get_schemas()
        logger.debug(f"{self.agent_name} 已加载 {self.tool_registry.count()} 个工具")

        self.context_manager = ContextManager(
            context_window_tokens=self.model_max_context,
            max_completion_tokens=self.max_completion_tokens,
        )

        self.compressor = LLMContextCompressor(model=self.model)

    async def run(self, channel_id: str, input_q: asyncio.Queue, output_q: asyncio.Queue) -> None:
        """
        运行 Agent 主逻辑处理
        """
        _running = True 
        local_history: list[dict] = [] 

        todo_counter = {
            "no_update_count": 0,  # 未更新计数
            "has_active_todo": False,  # 是否有活跃todo
        }

        channel_workspace = Path.home() / ".cheerclaw" / channel_id / "workspace"
        channel_workspace.mkdir(parents=True, exist_ok=True)

        # 获取 channel 信息摘要
        channel_info = ""
        if self.channel_info_manager:
            channel_info = self.channel_info_manager.build_summary()

        system_prompt = self.context_manager._build_system_prompt(
            always_content=self.always_content,
            skills_summary_content=self.skills_summary,
            channel_id=channel_id,
            workspace=channel_workspace,
            channel_info=channel_info,
        )

        logger.debug(f"{self.agent_name} System message ({len(system_prompt)} chars):\n{system_prompt}")

        try:
            loaded_history = self.context_manager.load_history(channel_workspace)
            if loaded_history:
                local_history.extend(loaded_history)
                meta = self.context_manager.load_meta(channel_workspace)
                compress_history = meta.get("compress_history", [])
                compress_idx = compress_history[-1] if compress_history else 0
                await output_q.put((channel_id, f"📝 已加载 {len(local_history)} 条历史消息（当前压缩点: {compress_idx}）"))
        except Exception as e:
            logger.debug(f"{self.agent_name} 加载历史失败: {e}")

        if self.client:
            # 发送启动消息
            await output_q.put((channel_id, f"Agent {self.agent_name} channel:{channel_id} 已启动✅ 已连接到模型: {self.model}"))

        # 主消息处理循环
        while _running:
            try:
                # 从输入队列获取用户消息
                user_input = await input_q.get()

                await self._process_user_input(
                    user_input=user_input,
                    channel_id=channel_id,
                    input_q=input_q,
                    output_q=output_q,
                    local_history=local_history,
                    system_prompt=system_prompt,
                    channel_workspace=channel_workspace,
                    todo_counter=todo_counter,
                )
                input_q.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"{self.agent_name} 处理消息异常: {e}")
                await output_q.put((channel_id, f"[错误] Agent 处理异常: {e}"))

    async def _process_user_input(
        self,
        user_input: str,
        channel_id: str,
        input_q: asyncio.Queue,
        output_q: asyncio.Queue,
        local_history: list[dict],
        system_prompt: str,
        channel_workspace: Path,
        todo_counter: dict,
    ) -> None:
        """
        处理用户输入消息
        user_input: 用户输入
        channel_id: 通道ID
        input_q: 输入队列
        output_q: 输出队列
        local_history: 当前协程的对话历史
        channel_workspace: 当前 channel 的 workspace 路径
        """
        if not user_input:
            return

        # 处理命令
        if user_input.startswith("/"):
            await self._handle_command(
                command=user_input[1:],
                channel_id=channel_id,
                output_q=output_q,
                local_history=local_history,
                channel_workspace=channel_workspace,
            )
            return

        # 处理普通消息
        await self._handle_user_message(
            user_input=user_input,
            channel_id=channel_id,
            input_q=input_q,
            output_q=output_q,
            local_history=local_history,
            system_prompt=system_prompt,
            channel_workspace=channel_workspace,
            todo_counter=todo_counter,
        )

    async def _handle_user_message(
        self,
        user_input: str,
        channel_id: str,
        input_q: asyncio.Queue,
        output_q: asyncio.Queue,
        local_history: list[dict],
        system_prompt: str,
        channel_workspace: Path,
        todo_counter: dict,
    ) -> None:
        """
        处理用户文本消息
        user_input: 用户输入
        channel_id: 通道ID
        input_q: 输入队列
        output_q: 输出队列
        local_history: 当前协程的对话历史
        system_prompt: 系统提示词
        channel_workspace: 当前 channel 的 workspace 路径
        """
        # 发送思考中消息
        await output_q.put((channel_id, "[思考中...]"))

        # 添加用户消息到历史（带时间戳）
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_input_with_timestamp = f"[{timestamp}] {user_input}"
        local_history.append({"role": "user", "content": user_input_with_timestamp})

        tools_schemas = self._tools_schemas
        max_iterations = 50
        iteration = 0
        final_reply = ""
        # 循环外初始化计数器
        todo_counter["no_update_count"] = 0

        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"Channel {channel_id} 当前一条用户提问的第 {iteration} 轮 llm 循环")

            # ==========  1、每次循环前检测压缩点（工具调用会增加tokens） ==========
            # 从 meta 读取压缩历史（每次循环都获取最新的）
            meta = self.context_manager.load_meta(channel_workspace)
            compress_history = meta.get("compress_history", [])
            compress_idx = compress_history[-1] if compress_history else 0

            # 实时读取长期记忆并拼接到 system_prompt
            memory_content = load_memory_content(channel_workspace)
            full_system_prompt = system_prompt.format(memory_content=memory_content)

            messages_for_check = [
                {"role": "system", "content": full_system_prompt},
                *local_history[compress_idx:],
            ]
            stats = self.context_manager.get_context_stats(messages_for_check)

            if stats["needs_truncation"]:
                # 计算新压缩点：只保留安全预算一半的上下文
                safe_budget = self.context_manager.get_safe_context_budget()
                tokens_to_remove = stats["total_tokens"] - (safe_budget // 2)
                new_compress_idx = self.context_manager.calculate_compress_point(
                    messages=local_history,
                    current_compress_idx=compress_idx,
                    tokens_to_remove=tokens_to_remove,
                )
                # 立即更新压缩点
                compress_idx = new_compress_idx
                compress_history.append(compress_idx)
                meta["compress_history"] = compress_history
                self.context_manager.save_meta(channel_workspace, meta)
                await output_q.put((channel_id, f"🔄 压缩点已更新, 压缩对话至索引 {compress_idx}"))

                # 同时触发后台压缩协程，传入已计算的压缩点
                asyncio.create_task(
                    self._compress_context_background(
                        channel_id=channel_id,
                        local_history=local_history,
                        output_q=output_q,
                        new_compress_idx=new_compress_idx,
                        system_prompt=system_prompt,
                        channel_workspace=channel_workspace,
                    )
                )


            # ==========  2、调用大模型  ==========
            # 构建发送给大模型的消息（system + 压缩点之后的历史）
            messages = [
                {"role": "system", "content": full_system_prompt},
                *local_history[compress_idx:],
            ]
            logger.debug(f"[_process_user_input] 第{iteration}轮准备调用LLM, 消息数: {len(messages)}")
            response = await self._call_llm(messages, tools=tools_schemas)
            logger.debug(f"[_process_user_input] 第{iteration}轮LLM调用完成")
            logger.debug(f"LLM Response: {response}")
            # 向队列推送推理内容
            # if response.get("reasoning_content"):
            #     await output_q.put((channel_id, f"[思考过程]: {response['reasoning_content']}"))
            if response.get("reasoning_content"):
                logger.debug(f"[思考过程] {response['reasoning_content']}")

            # ==========  3、调用大模型后  ==========
            active_todo = self.todo_manager.get_active_todo(channel_workspace)
            if active_todo:  # 有活跃 Todo 才继续判断
                has_update_todo = response.get("tool_calls") and any(tc.get("name") == "update_todo" for tc in response["tool_calls"])
                if has_update_todo:
                    todo_counter["no_update_count"] = 0
                    # 如果 todo 被完成，下次循环 active_todo 会是 None
                else:
                    todo_counter["no_update_count"] += 1
                    if todo_counter["no_update_count"] > 12:
                        # 插入提醒更新todolist消息
                        todo_status = self.todo_manager.render(active_todo)
                        reminder_msg = f"[系统提醒]: 已执行 {todo_counter['no_update_count']} 轮 LLM 调用但均未更新todo list。上次更新后的任务状态:\n{todo_status} \n判断当前是否应该更新任务状态。"
                        local_history.append({"role": "user", "content": reminder_msg})
                        # 发送提醒消息到输出队列
                        # await output_q.put((channel_id, reminder_msg))
                        todo_counter["no_update_count"] = 0  # 重置计数器
                        
            # (1) llm结果是工具执行
            if response.get("tool_calls"):
                tool_calls = response["tool_calls"]
                # 工具确认检查 执行
                logger.debug(f"[_process_user_input] 开始执行工具, 工具数: {len(tool_calls)}")
                await self._execute_tools_with_confirmation(
                    tool_calls=tool_calls,
                    local_history=local_history,
                    channel_id=channel_id,
                    input_q=input_q,
                    output_q=output_q,
                    channel_workspace=channel_workspace,
                )
                logger.debug(f"[_process_user_input] 工具执行完成, 历史消息数: {len(local_history)}")
                logger.debug(f"[_process_user_input] 继续下一轮循环")
                continue
            # (2) llm结果是文本输出
            else:
                # 无/不再工具调用 助手回复
                final_reply = response.get("content", "")
                if not final_reply:
                    final_reply = "（任务已执行完成，回复为空）"
                # 添加模型回复到历史（带时间戳）
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_reply_with_timestamp = f"[{timestamp}] {final_reply}"
                local_history.append({"role": "assistant", "content": final_reply_with_timestamp})
                break
        else:
            # 超过工具轮次上限还未得到助手回复，基于工具调用结果生成总结
            await output_q.put((channel_id, "🔄 [主Agent]达到最大迭代次数，正在生成任务总结..."))
            # 构建包含 system message 和当前压缩点之后消息 以命中 KV Cache
            # 实时读取长期记忆
            memory_content = load_memory_content(channel_workspace)
            full_system_prompt = system_prompt.format(memory_content=memory_content)
            messages_for_summary = [
                {"role": "system", "content": full_system_prompt},
                *local_history[compress_idx:],
            ]
            final_reply = await generate_summary_from_tools(
                messages=messages_for_summary,
                client=self.client,
                model=self.model,
            )
            # 添加总结回复到历史（带时间戳）
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            final_reply_with_timestamp = f"[{timestamp}] {final_reply}"
            local_history.append({"role": "assistant", "content": final_reply_with_timestamp})

        # 保存完整对话历史到本地文件（覆盖写入）
        try:
            self.context_manager.save_history(channel_workspace, local_history)
        except Exception as e:
            logger.debug(f"保存对话交互历史失败: {e}")

        # 发送最终回复
        await output_q.put((channel_id, final_reply))

    async def _compress_context_background(
        self,
        channel_id: str,
        local_history: list[dict],
        output_q: asyncio.Queue,
        new_compress_idx: int,
        system_prompt: str,
        channel_workspace: Path,
    ) -> None:
        """
        后台压缩总结
        channel_id: 通道ID
        local_history: 当前协程的对话历史
        output_q: 输出队列
        new_compress_idx: 新的压缩点索引
        system_prompt: 系统提示词
        channel_workspace: 当前 channel 的 workspace 路径
        """
        try:
            await output_q.put((channel_id, "🔄 正在压缩对话历史..."))

            # 从meta读取已更新的压缩点
            meta = self.context_manager.load_meta(channel_workspace)
            compress_history = meta.get("compress_history", [])
            if not compress_history:
                await output_q.put((channel_id, "✅ 压缩点为空，跳过压缩"))
                return

            current_compress_idx = compress_history[-1]
            last_compress_idx = compress_history[-2] if len(compress_history) >= 2 else 0

            # 检查是否有足够的消息需要压缩
            if current_compress_idx <= last_compress_idx:
                # 移除无效的压缩点
                if compress_history[-1] == new_compress_idx:
                    compress_history.pop()
                    meta["compress_history"] = compress_history
                    self.context_manager.save_meta(channel_workspace, meta)
                await output_q.put((channel_id, "✅ 压缩区间无效，已回滚压缩点"))
                return

            # 验证传入的参数与meta一致
            if current_compress_idx != new_compress_idx:
                logger.debug(f"[压缩点不一致: meta={current_compress_idx}, param={new_compress_idx}")

            compressed_content = await self.compressor.compress_from_point(
                channel_workspace=channel_workspace,
                local_history=local_history,
                last_compress_idx=last_compress_idx,
                new_compress_idx=current_compress_idx,
            )

            # 更新meta的压缩时间
            meta["compressed_at"] = asyncio.get_event_loop().time()
            self.context_manager.save_meta(channel_workspace, meta)

            # 保存完整历史到文件（覆盖写入）
            self.context_manager.save_history(channel_workspace, local_history)

            # 获取压缩后的统计信息（从新的压缩点开始）
            messages_after = [
                {"role": "system", "content": system_prompt},
                *local_history[current_compress_idx:],
            ]
            stats_after = self.context_manager.get_context_stats(messages_after)

            # 发送压缩完成通知
            removed_count = current_compress_idx - last_compress_idx
            await output_q.put((
                channel_id,
                f"✅ 历史压缩完成："
                f"移除 {removed_count} 条消息（索引 {last_compress_idx} → {current_compress_idx}），"
                f"当前 {stats_after['total_tokens']} tokens"
            ))

        except Exception as e:
            logger.debug(f"压缩历史失败: {e}")
            await output_q.put((channel_id, f"⚠️ 历史压缩失败: {e}"))

    async def _handle_command(
        self,
        command: str,
        channel_id: str,
        output_q: asyncio.Queue,
        local_history: list[dict],
        channel_workspace: Path,
    ) -> None:
        """
        处理用户命令
        command: 命令
        channel_id: 通道ID
        output_q: 输出队列
        local_history: 当前协程的对话历史
        channel_workspace: 当前 channel 的 workspace 路径
        """
        if command == "clear":
            local_history.clear()
            # 同时清空文件中的历史和压缩历史
            try:
                self.context_manager.save_history(channel_workspace, [])
                logger.debug(f"已清空原始对话历史jsonl")
                # 重置压缩历史列表
                meta = self.context_manager.load_meta(channel_workspace)
                meta["compress_history"] = []
                self.context_manager.save_meta(channel_workspace, meta)
                logger.debug("已清空压缩点信息")
                # 清空压缩后的历史文件
                self.compressor.clear_compressed_history(channel_workspace)
                await output_q.put((channel_id, "对话历史和记忆已清空（包括原始对话、history、memory）"))
            except Exception as e:
                await output_q.put((channel_id, f"对话历史已清空，但文件清理失败: {e}"))
        elif command == "tools":
            tools_info = self.tool_registry.get_infos()
            tool_list = "\n".join([f"  - {name}: {info['description'][:50]}..." for name, info in tools_info.items()])
            await output_q.put((channel_id, f"已加载工具:\n{tool_list}"))
        elif command == "skills":
            skills = self.skill_loader.list_skills()
            if skills:
                lines = ["已加载技能:"]
                for s in skills:
                    status = "✓" if s["available"] else "✗"
                    lines.append(f"  {status} {s['name']}: {s['description']}")
                await output_q.put((channel_id, "\n".join(lines)))
            else:
                await output_q.put((channel_id, "没有可用的技能"))
        elif command == "history":
            # 展示最近压缩点到当前对话之间的历史（大模型能看到的对话历史）
            try:
                meta = self.context_manager.load_meta(channel_workspace)
                compress_history = meta.get("compress_history", [])
                compress_idx = compress_history[-1] if compress_history else 0
                visible_history = local_history[compress_idx:]

                # 使用工具函数格式化历史
                result = format_history_for_display(
                    visible_history=visible_history,
                    compress_idx=compress_idx,
                    total_count=len(local_history),
                )
                await output_q.put((channel_id, result))
            except Exception as e:
                await output_q.put((channel_id, f"⚠️ 获取对话历史失败: {e}"))
        else:
            await output_q.put((channel_id, f"未知命令: /{command}"))


    # 执行工具获取结果（确认/不确认）
    async def _execute_tools_with_confirmation(
        self,
        tool_calls: list,
        local_history: list,
        channel_id: str,
        input_q: asyncio.Queue,
        output_q: asyncio.Queue,
        channel_workspace: Path,
    ) -> None:
        """
        执行工具并处理确认
        tool_calls: 工具调用列表
        local_history: 对话历史（会被修改添加工具结果）
        channel_id: 通道ID
        input_q: 输入队列
        output_q: 输出队列
        channel_workspace: workspace 路径
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

        # 构建并添加 assistant 消息（包含所有工具调用）
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
            ],
        }
        local_history.append(assistant_msg)

        # 步骤1: 执行所有不需要确认的工具，结果立即追加到历史
        for tc in no_confirm_tools:
            # 发送工具调用通知
            await output_q.put((channel_id, f"[使用工具] {tc['name']}"))
            logger.debug(f"[工具执行] 工具名: {tc['name']}, 参数: {tc['arguments']}")

            # 准备工具参数
            tool_args = dict(tc["arguments"])
            if tc["name"] == "update_todo":
                tool_args["channel_workspace"] = channel_workspace
            if tc["name"] == "use_subagent":
                tool_args["channel_id"] = channel_id
                tool_args["input_q"] = input_q
                tool_args["output_q"] = output_q
                tool_args["channel_workspace"] = channel_workspace
            if tc["name"] == "send_message":
                tool_args["output_q"] = output_q

            result = await self.tool_registry.execute(tc["name"], tool_args)
            if result.success:
                # update_todo 工具展示详细结果
                if tc["name"] == "update_todo":
                    await output_q.put((channel_id, f"[工具执行成功] {tc['name']}\n{result.data}"))
                else:
                    await output_q.put((channel_id, f"[工具执行成功] {tc['name']}"))
                logger.debug(f"[工具结果] 工具名: {tc['name']}, 结果: {str(result.data)[:200]}")
            else:
                await output_q.put((channel_id, f"[工具执行失败] {tc['name']}"))
                logger.debug(f"[工具结果] 工具名: {tc['name']}, 错误: {str(result.error)[:200]}")

            # 立即添加工具结果到历史
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": str(result.data if result.success else result.error),
            }
            local_history.append(tool_msg)

        # 步骤2: 逐个处理需要确认的工具，结果立即追加到历史
        for tc, reason in need_confirm_tools:
            tool_name = tc["name"]
            arguments = tc["arguments"]

            # 发送工具调用通知
            await output_q.put((channel_id, f"[使用工具] {tool_name}"))
            logger.debug(f"[工具执行-需确认] 工具名: {tool_name}, 参数: {arguments}")

            # 发送确认请求
            confirm_msg = self._format_tool_confirm_message(tool_name, arguments, reason)
            await output_q.put((channel_id, confirm_msg))
            
            # 等待用户回复（一直等待）
            user_reply = await input_q.get()
            if user_reply and user_reply.strip() == "是":
                # 准备工具参数
                tool_args = dict(arguments)
                if tool_name == "update_todo":
                    tool_args["channel_workspace"] = channel_workspace
                if tool_name == "use_subagent":
                    tool_args["channel_id"] = channel_id
                    tool_args["input_q"] = input_q
                    tool_args["output_q"] = output_q
                    tool_args["channel_workspace"] = channel_workspace
                if tool_name == "send_message":
                    tool_args["output_q"] = output_q

                result = await self.tool_registry.execute(tool_name, tool_args)
                status = "成功" if result.success else "失败"
                # update_todo 工具展示详细结果
                if tool_name == "update_todo":
                    await output_q.put((channel_id, f"[工具执行{status}] {tool_name}\n{result.data}"))
                else:
                    await output_q.put((channel_id, f"[工具执行{status}] {tool_name}"))
                if result.success:
                    logger.debug(f"[工具结果-需确认] 工具名: {tool_name}, 结果: {str(result.data)[:200]}")
                else:
                    logger.debug(f"[工具结果-需确认] 工具名: {tool_name}, 错误: {str(result.error)[:200]}")
            else:
                # 构建详细的取消消息，包含用户的回复内容
                user_response = user_reply.strip() if user_reply else "（无回复/超时）"
                cancel_msg = f"工具 {tool_name} 执行被取消。原因：用户未确认执行。用户回复：「{user_response}」"
                result = ToolResult(tool_name=tool_name, success=True, data=cancel_msg)
                await output_q.put((channel_id, f"[工具取消] {tool_name}"))
                logger.debug(f"[工具结果-需确认] 工具名: {tool_name}, 状态: 用户取消")

            # 立即添加工具结果到历史
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tool_name,
                "content": str(result.data if result.success else result.error),
            }
            local_history.append(tool_msg)

    def _format_tool_confirm_message(self, tool_name: str, arguments: dict, reason: str) -> str:
        """
        格式化工具确认消息
        """
        return format_tool_confirm_message(tool_name, arguments, reason, agent_tag="")

    async def _call_llm(self, messages: list[dict], tools: Optional[list] = None) -> dict:
        """
        调用 OpenAI API
        """
        return await call_llm(
            client=self.client,
            model=self.model,
            messages=messages,
            tools=tools,
        )


