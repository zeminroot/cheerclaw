#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   cli_channel.py
@Author  :   zemin
@Desc    :   CLI终端输入输出通道
'''

import sys
import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

# 初始化 Rich 控制台
console = Console(file=sys.stdout, force_terminal=True, color_system="auto")

# CLI 专用的发送队列（接收输出消息）
CLI_SEND_QUEUE = asyncio.Queue()

# 全局输入队列引用
_global_in_queue = None


def set_global_in_queue(queue: asyncio.Queue):
    global _global_in_queue
    _global_in_queue = queue


async def cli_input_channel(global_in_queue: asyncio.Queue = None):
    """
    CLI终端输入通道
    从终端读取用户输入，发送到本地缓冲队列（支持连续输入）
    global_in_queue: 全局输入队列，用于接收用户输入
    """
    if global_in_queue:
        set_global_in_queue(global_in_queue)

    if not _global_in_queue:
        raise RuntimeError("全局输入队列未设置，请先调用 set_global_in_queue()")

    current_channel = "cli"
    session = PromptSession()

    with patch_stdout():
        while True:
            try:
                user_input = await session.prompt_async("")
                user_input = user_input.strip()
                if not user_input:
                    continue

                # 异步发送消息（不阻塞输入）
                asyncio.create_task(
                    _global_in_queue.put((current_channel, "cli", "本地终端输入输出", user_input))
                )

            except (EOFError, KeyboardInterrupt):
                print("\n[CLI输入] 收到中断信号，退出")
                break


async def cli_output_sender():
    while True:
        try:
            msg = await CLI_SEND_QUEUE.get()
            await handle_cli_output(msg)
        except Exception as e:
            print(f"\n[CLI输出] 错误: {e}")


async def handle_cli_output(msg: str):
    """
    处理CLI输出消息
    msg: 要显示的消息内容
    """
    if "⚠️ 安全确认" in msg:
        console.print(Panel(
            msg,
            title="🔒 安全确认请求",
            title_align="left",
            border_style="yellow",
            padding=(1, 2),
            style="on grey93"  # 浅蓝灰色背景
        ))
    elif "[思考中...]" in msg:
        console.print(Panel(
            "[bold cyan]💭 思考中...[/bold cyan]",
            border_style="dim",
            padding=(0, 1),
            style="on grey93"  # 浅蓝灰色背景
        ))
    else:
        console.print(Panel(
            Markdown(msg),
            border_style="dim",
            padding=(0, 1),
            style="on grey93"  # 浅蓝灰色背景
        ))

    # 添加分割线
    line_width = max(int(console.width * 0.9), 20)
    console.print("[dim]" + "─" * line_width + "[/dim]")
