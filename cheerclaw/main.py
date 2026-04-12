#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   main.py
@Author  :   zemin
@Desc    :   CheerClaw 主入口
'''

import asyncio
import sys
from pathlib import Path
from typing import Dict
from loguru import logger
from cheerclaw.agent.main_agent import AgentApp
from cheerclaw.show_style.welcome import print_welcome_box

# 关闭日志输出
logger.remove()
# 启用日志
# logger.add(sys.stderr, level="INFO")
from cheerclaw.config.config_loader import load_config
from cheerclaw.utils.channel_info import ChannelInfoManager

from cheerclaw.channels import (
    CLI_SEND_QUEUE,
    CHANNEL_QQ_SEND_QUEUE,
    CHANNEL_FEISHU_SEND_QUEUE,
)

CHEERCLAW_DIR = Path.home() / ".cheerclaw"
RUNSPACE = Path.cwd()

CHEERCLAW_DIR.mkdir(parents=True, exist_ok=True)

# 全局队列接收所有用户的原始消息（做路由分发）
GLOBAL_IN_QUEUE = asyncio.Queue()
# 全局队列接收Agent输出的原始消息（Agent对所有channel的输出都到这里）
GLOBAL_OUTPUT_QUEUE = asyncio.Queue()


class MainCheerClaw:
    def __init__(self):
        # 每个用户独立输入队列
        self.channel_input_queues: Dict[str, asyncio.Queue] = {}
        self.channel_tasks: Dict[str, asyncio.Task] = {}
        # Channel 信息管理器
        self.channel_info_manager = ChannelInfoManager(clawspace=CHEERCLAW_DIR)
        # 预注册默认 channels
        self._register_default_channels()
        # 加载配置并创建共享的 Agent 实例
        self.config = load_config(config_path=CHEERCLAW_DIR / "config.json")
        self.main_agent_process = AgentApp(
            config=self.config,
            runspace=RUNSPACE,
            channel_info_manager=self.channel_info_manager
        )

    def _register_default_channels(self):
        """预注册默认的系统 channels"""
        defaults = [
            ("cli", "cli", "本地终端channel，可发送消息，可接收消息"),
            ("cron", "cron", "定时任务发消息channel，只发送消息给cheerclaw，不能接收消息"),
        ]
        for channel_id, source, describe in defaults:
            self.channel_info_manager.register_channel(channel_id, source, describe)

    def get_input_queue(self, channel_id: str) -> asyncio.Queue:
        if channel_id not in self.channel_input_queues:
            self.channel_input_queues[channel_id] = asyncio.Queue()
        return self.channel_input_queues[channel_id]

    # 创建用户独立业务协程
    def create_channel_task(self, channel_id: str):
        if channel_id not in self.channel_tasks:
            task = asyncio.create_task(self.business_coroutine(channel_id))
            self.channel_tasks[channel_id] = task

    # 用户独立业务协程（完全隔离）
    async def business_coroutine(self, channel_id: str):
        # 私有输入队列，全局输出队列
        input_q = self.get_input_queue(channel_id)
        await self.main_agent_process.run(channel_id=channel_id, input_q=input_q, output_q=GLOBAL_OUTPUT_QUEUE)

    # 注册 channel 信息
    def _register_channel_from_message(self, channel_id: str, channel_source: str, channel_describe: str):
        if not self.channel_info_manager.is_valid_channel(channel_id):
            self.channel_info_manager.register_channel(channel_id, channel_source, channel_describe)
            logger.info(f"[MainCheerClaw] 注册新 Channel: {channel_id} ({channel_source})")



async def dispatcher(cheer_claw: MainCheerClaw):
    """
    消息分发器
    从 GLOBAL_IN_QUEUE 接收消息，根据 channel_id 路由到对应的私有输入队列
    消息格式: (channel_id, channel_source, channel_describe, message)
    """
    while True:
        data = await GLOBAL_IN_QUEUE.get()
        channel_id, channel_source, channel_describe, msg = data

        cheer_claw._register_channel_from_message(channel_id, channel_source, channel_describe)

        cheer_claw.create_channel_task(channel_id)

        await cheer_claw.get_input_queue(channel_id).put(msg)
        GLOBAL_IN_QUEUE.task_done()


async def channel_output_task():
    """
    监听全局输出队列，根据 channel_id 进行不同处理
    - cli (CLI): 推送到 CLI_SEND_QUEUE，由 cli_output_sender 处理
    - qq_* (QQ): 推送到 CHANNEL_QQ_SEND_QUEUE，由 qq_channel 处理
    - feishu_* (飞书): 推送到 CHANNEL_FEISHU_SEND_QUEUE，由 feishu_channel 处理
    消息格式: (channel_id, msg)
    """
    while True:
        try:
            channel_id, msg = await GLOBAL_OUTPUT_QUEUE.get()

            if channel_id == "cli":
                await CLI_SEND_QUEUE.put(msg)
            elif channel_id.startswith("qq_"):
                await CHANNEL_QQ_SEND_QUEUE.put((channel_id, msg))
            elif channel_id.startswith("feishu_"):
                await CHANNEL_FEISHU_SEND_QUEUE.put((channel_id, msg))
            else:
                logger.info(f"[未知Channel {channel_id}] {msg}")

            GLOBAL_OUTPUT_QUEUE.task_done()

        except Exception as e:
            logger.error(f"[输出处理错误] error={e}")
