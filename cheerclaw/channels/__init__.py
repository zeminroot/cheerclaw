#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   __init__.py
@Author  :   zemin
@Desc    :   输入输出通道模块
'''

from .cli_channel import cli_input_channel, cli_output_sender, CLI_SEND_QUEUE
from .cron_channel import cron_scheduler_task
from .qq_channel import qq_channel, CHANNEL_QQ_SEND_QUEUE
from .feishu_channel import feishu_channel, CHANNEL_FEISHU_SEND_QUEUE

__all__ = [
    # CLI 终端通道
    'cli_input_channel',
    'cli_output_sender',
    'CLI_SEND_QUEUE',
    # 定时任务通道
    'cron_scheduler_task',
    # QQ Bot 通道
    'qq_channel',
    'CHANNEL_QQ_SEND_QUEUE',
    # 飞书 Bot 通道
    'feishu_channel',
    'CHANNEL_FEISHU_SEND_QUEUE',
]
