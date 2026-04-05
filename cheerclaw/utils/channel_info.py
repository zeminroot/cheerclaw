#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   channel_info.py
@Author  :   zemin
@Desc    :   None
'''

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from loguru import logger


@dataclass
class ChannelInfo:
    """Channel 信息数据类"""
    channel_id: str
    channel_source: str
    channel_describe: str


class ChannelInfoManager:

    def __init__(self, clawspace: Optional[Path] = None):
        """
        clawspace: CheerClaw 主目录，默认为 ~/.cheerclaw
        """
        if clawspace is None:
            clawspace = Path.home() / ".cheerclaw"

        self.clawspace = Path(clawspace)
        self.clawspace.mkdir(parents=True, exist_ok=True)

        self.info_file = self.clawspace / "channel_info.json"
        self._channels: Dict[str, ChannelInfo] = {}
        self._lock = threading.Lock()  # 保护并发写入

        self._load()

    def _load(self) -> None:
        if not self.info_file.exists():
            return

        try:
            with open(self.info_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for item in data:
                channel_info = ChannelInfo(
                    channel_id=item['channel_id'],
                    channel_source=item['channel_source'],
                    channel_describe=item['channel_describe']
                )
                self._channels[channel_info.channel_id] = channel_info
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error(f"[ChannelInfo] 加载失败: {e}")

    def _save(self) -> None:
        try:
            data = [
                {
                    'channel_id': info.channel_id,
                    'channel_source': info.channel_source,
                    'channel_describe': info.channel_describe
                }
                for info in self._channels.values()
            ]

            with open(self.info_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"[ChannelInfo] 保存失败: {e}")

    def register_channel(self, channel_id: str, channel_source: str, channel_describe: str) -> bool:
        """注册新的 Channel
        channel_id: Channel 唯一标识
        channel_source: Channel 来源（如 'cli', 'qq', 'socket'）
        channel_describe: Channel 描述
        返回: 是否成功注册（已存在返回 False）
        """
        with self._lock:
            if channel_id in self._channels:
                return False

            self._channels[channel_id] = ChannelInfo(
                channel_id=channel_id,
                channel_source=channel_source,
                channel_describe=channel_describe
            )
            self._save()
            return True

    def unregister_channel(self, channel_id: str) -> bool:
        """注销 Channel
        channel_id: Channel 唯一标识
        返回: 是否成功注销
        """
        data = [
            {
                'channel_id': info.channel_id,
                'channel_source': info.channel_source,
                'channel_describe': info.channel_describe
            }
            for info in self._channels.values()
        ]
        return json.dumps(data, ensure_ascii=False, indent=2)
