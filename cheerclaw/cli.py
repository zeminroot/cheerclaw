#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   cli.py
@Author  :   zemin
@Desc    :   
CheerClaw 命令行入口
两种启动模式:
- cheerclaw local: 本地 CLI 交互模式
- cheerclaw online: 在线/后台运行模式（ QQ 交互）
'''

import argparse
import asyncio
import sys
from pathlib import Path
from loguru import logger

# 添加项目根目录到路径
CHEERCLAW_DIR = Path.home() / ".cheerclaw"
CHEERCLAW_DIR.mkdir(parents=True, exist_ok=True)

# 关闭日志处理器
logger.remove()


from cheerclaw.main import MainCheerClaw, dispatcher, channel_output_task, GLOBAL_IN_QUEUE, GLOBAL_OUTPUT_QUEUE, CHEERCLAW_DIR, RUNSPACE
from cheerclaw.channels import (
    cli_input_channel,
    cli_output_sender,
    cron_scheduler_task,
    qq_channel,
)
from cheerclaw.show_style.welcome import print_welcome_box


def cmd_local(args):
    """
    本地 CLI 模式启动
    - 启动 CLI Channel（终端交互）
    - 不启动 QQ Channel
    - 显示欢迎界面
    """
    from cheerclaw.config.config_loader import (
        load_config,
        validate_config_for_mode,
        interactive_config_init,
    )

    # 加载并验证配置
    config_path = Path.home() / ".cheerclaw" / "config.json"
    config = load_config(config_path)

    is_valid, missing = validate_config_for_mode(config, "local")
    if not is_valid:
        print(f"缺少关键配置项: {', '.join(missing)}，请填写配置信息")
        config = interactive_config_init("local", config, missing)

    print_welcome_box()

    async def run_local():
        cheer_claw = MainCheerClaw()

        # 构建要启动的协程列表（只启动 CLI）
        coroutines = [
            dispatcher(cheer_claw),
            channel_output_task(),
            cron_scheduler_task(GLOBAL_IN_QUEUE, CHEERCLAW_DIR),
            cli_input_channel(GLOBAL_IN_QUEUE),
            cli_output_sender(),
        ]

        # 启动所有协程
        await asyncio.gather(*coroutines)

    try:
        asyncio.run(run_local())
    except KeyboardInterrupt:
        print("\n👋 再见！")
        sys.exit(0)


def cmd_online(args):
    """
    在线/后台模式启动（只与 QQ 交互）
    - 不启动 CLI Channel
    - 启动 QQ Channel（在线交互）
    - 输出启动标志后持续后台运行
    """
    from cheerclaw.config.config_loader import (
        load_config,
        validate_config_for_mode,
        interactive_config_init,
    )

    # 加载并验证配置
    config_path = Path.home() / ".cheerclaw" / "config.json"
    config = load_config(config_path)

    is_valid, missing = validate_config_for_mode(config, "online")
    if not is_valid:
        print(f"缺少关键配置项: {', '.join(missing)}，请填写配置信息")
        config = interactive_config_init("online", config, missing)

    # 简化版启动标志
    print("=" * 50)
    print("🚀 CheerClaw Online Mode Started")
    print("=" * 50)
    print(f"📁 Workspace: {RUNSPACE}")
    print(f"⚙️  Config Dir: {CHEERCLAW_DIR}")
    print("🤖 QQ Bot 已就绪，等待消息...")
    print("-" * 50)

    async def run_online():
        cheer_claw = MainCheerClaw()

        # 构建要启动的协程列表（只启动 QQ，不启动 CLI）
        coroutines = [
            dispatcher(cheer_claw),
            channel_output_task(),
            cron_scheduler_task(GLOBAL_IN_QUEUE, CHEERCLAW_DIR),
            qq_channel(GLOBAL_IN_QUEUE, cheer_claw.config.qq),
        ]

        logger.info("[Main] QQ Channel 已启动")

        # 启动所有协程
        await asyncio.gather(*coroutines)

    try:
        asyncio.run(run_online())
    except KeyboardInterrupt:
        print("\n👋 CheerClaw 已停止")
        sys.exit(0)


def main():
    """
    主命令行入口
    """
    parser = argparse.ArgumentParser(
        prog="cheerclaw",
        description="CheerClaw - 灵活的 AI Agent 框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  cheerclaw local         # 启动本地 CLI 交互模式
  cheerclaw online        # 启动在线/后台模式（只与 QQ 交互）
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # local 子命令
    local_parser = subparsers.add_parser(
        "local",
        help="本地 CLI 交互模式（启动终端交互）"
    )
    local_parser.set_defaults(func=cmd_local)

    # online 子命令
    online_parser = subparsers.add_parser(
        "online",
        help="在线/后台运行模式（只与 QQ 交互）"
    )
    online_parser.set_defaults(func=cmd_online)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
