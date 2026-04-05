#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   send_message.py
@Author  :   zemin
@Desc    :   发送消息工具
'''

from typing import Any, Optional
import asyncio
from cheerclaw.tools_module.base import Tool
from cheerclaw.utils.channel_info import ChannelInfoManager


class SendMessageTool(Tool):

    def __init__(self, channel_info_manager: Optional[ChannelInfoManager] = None):
        self.channel_info_manager = channel_info_manager

    @property
    def name(self) -> str:
        return "send_message"

    @property
    def description(self) -> str:
        return """向指定的 channel_id 发送消息。

使用场景：
- 需要向其他通道发送通知或消息时
- 需要与特定通道的用户通信时
- 需要将信息转发给指定通道时

注意：channel_id 必须是已连接的通道标识符（可通过 system prompt 中的"已连接的 Channels"查看）
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "目标通道ID，必须是已连接的 channel（如 'channel1', 'qq_xxx'）"
                },
                "message": {
                    "type": "string",
                    "description": "要发送的消息内容"
                }
            },
            "required": ["channel_id", "message"]
        }

    async def execute(self, channel_id: str, message: str, **kwargs) -> Any:
        """执行消息发送
        channel_id: 目标通道ID
        message: 要发送的消息内容
        **kwargs: 包含 output_q (输出队列)
        返回: 发送结果
        """
        output_q = kwargs.get("output_q")
        if not output_q:
            return "错误: send_message 工具需要 output_q 参数"

        # 验证 channel_id 是否有效
        if self.channel_info_manager and not self.channel_info_manager.is_valid_channel(channel_id):
            all_channels = self.channel_info_manager.build_json_summary() if self.channel_info_manager else "[]"
            return f"错误: channel_id '{channel_id}' 不在已连接的 channel 列表中。\n已连接的 channels:\n{all_channels}"

        await output_q.put((channel_id, message))
        return f"消息已发送到 {channel_id}: {message[:50]}{'...' if len(message) > 50 else ''}"

