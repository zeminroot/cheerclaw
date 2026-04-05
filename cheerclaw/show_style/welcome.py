#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   welcome.py
@Author  :   zemin
@Desc    :   启动欢迎语展示
'''

from rich.console import Console
from rich.panel import Panel
from rich.align import Align


_console = Console()


def print_welcome_box():
    """
    打印 CheerClaw 欢迎框框
    """
    welcome_text = """        [bold cyan] 欢迎使用 CheerClaw！[/bold cyan]

[green]一款灵活的 AI Agent框架，支持多通道交互[/green]

[green]建议注册免费的tavily apikey 地址: https://app.tavily.com/home [/green]

[yellow]快捷键：[/yellow]
      • 输入 [bold]/clear[/bold] 清除对话历史
      • [bold]Ctrl+C[/bold] 退出程序

[dim]服务已启动...[/dim]"""

    centered_content = Align.center(welcome_text)

    _console.print()
    _console.print(
        Panel(
            centered_content,
            title="[bold magenta]🐷 CheerClaw AI Assistant 🐷[/bold magenta]",
            title_align="center",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    _console.print()
