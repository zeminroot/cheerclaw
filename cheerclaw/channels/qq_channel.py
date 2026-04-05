#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   qq_channel.py
@Author  :   zemin
@Desc    :   
qq bot通道
'''


import asyncio

# QQ Channel 专用的发送队列（接收输出消息，发送给 QQ）
CHANNEL_QQ_SEND_QUEUE = asyncio.Queue()

# 全局输入队列引用（由主模块注入）
_global_in_queue = None

# Channel 标识（用于注册到 ChannelInfoManager）
CHANNEL_SOURCE = "qq"
CHANNEL_DESCRIBE = "QQ机器人通道"


def set_global_in_queue(queue: asyncio.Queue):
    """
    设置全局输入队列
    """
    global _global_in_queue
    _global_in_queue = queue

# QQ Bot（可选依赖）
QQ_AVAILABLE = False
try:
    import botpy
    from botpy import Intents
    from botpy.message import C2CMessage, GroupMessage
    QQ_AVAILABLE = True
except ImportError:
    botpy = Intents = C2CMessage = GroupMessage = None

if QQ_AVAILABLE:
    class QQChannelClient(botpy.Client):
        """
        QQ Bot 客户端（继承 botpy.Client）
        """

        def __init__(self, global_in_queue: asyncio.Queue, chat_type_cache: dict):
            intents = Intents(public_messages=True, direct_message=True)
            super().__init__(intents=intents, ext_handlers=False)
            self.global_in_queue = global_in_queue
            self._chat_type_cache = chat_type_cache

        async def on_ready(self):
            """
            机器人已连接
            """
            print("[QQ Channel] QQ 机器人已连接")

        async def on_c2c_message_create(self, message: C2CMessage):
            """收到 C2C 消息"""
            await self._handle_message(message, is_group=False)

        async def on_group_at_message_create(self, message: GroupMessage):
            """收到群组 @ 消息"""
            await self._handle_message(message, is_group=True)

        async def on_direct_message_create(self, message):
            """收到私信消息"""
            await self._handle_message(message, is_group=False)

        async def _handle_message(self, message, is_group: bool = False):
            """处理收到的消息"""
            content = message.content or ""

            if is_group:
                chat_id = message.group_openid
                describe = f"QQ群组 {chat_id[:20]}"
            else:
                chat_id = str(getattr(message.author, "user_openid", "unknown"))
                describe = f"QQ用户 {chat_id[:20]}"

            # 生成 CheerClaw 格式的 channel_id
            channel_id = f"qq_{chat_id}"

            # 缓存 chat 类型用于发送时判断
            self._chat_type_cache[channel_id] = is_group

            # 推送到全局输入队列 (channel_id, channel_source, channel_describe, message)
            if self.global_in_queue:
                await self.global_in_queue.put((channel_id, "qq", describe, content.strip()))
                print(f"[QQ Channel] 收到消息 from {channel_id}: {content[:50]}")
else:
    QQChannelClient = None


async def qq_channel(global_in_queue: asyncio.Queue = None, qq_config=None):
    """
    QQ Bot 通道
    接收 QQ 消息 -> 生成 channel_id -> 推送到 GLOBAL_IN_QUEUE
    从 CHANNEL_QQ_SEND_QUEUE 取消息 -> 解析 channel_id -> 发送到 QQ
    global_in_queue: 全局输入队列，用于接收 QQ 消息
    qq_config: QQ 配置对象，包含 app_id 和 secret
    """
    if global_in_queue:
        set_global_in_queue(global_in_queue)

    if not _global_in_queue:
        raise RuntimeError("全局输入队列未设置")

    if not QQ_AVAILABLE:
        print("[QQ Channel] botpy 未安装，跳过 QQ Channel。运行: pip install qq-botpy")
        # 保持存活，不退出
        while True:
            await asyncio.sleep(60)

    # 从配置获取 QQ Bot 配置
    if qq_config:
        app_id = qq_config.app_id
        secret = qq_config.secret
    else:
        app_id = ""
        secret = ""

    if not app_id or not secret:
        print("[QQ Channel] QQ 配置未设置（config.json 中缺少 qq.app_id 或 qq.secret），QQ Channel 未启动")
        print("[QQ Channel] 请在 config.json 中添加:")
        print('  "qq": {"app_id": "your_app_id", "secret": "your_secret"}')
        # 保持存活，不退出
        while True:
            await asyncio.sleep(60)

    # chat_id -> is_group 缓存
    chat_type_cache: dict[str, bool] = {}

    # 创建 QQ 客户端
    client = QQChannelClient(_global_in_queue, chat_type_cache)

    # 启动接收和发送两个协程
    await asyncio.gather(
        _qq_bot_runner(client, app_id, secret),
        _qq_sender(client, chat_type_cache)
    )


async def _qq_bot_runner(client, app_id: str, secret: str):
    """
    运行 QQ Bot 连接（自动重连）
    """
    while True:
        try:
            print(f"[QQ Channel] 启动 QQ Bot...")
            await client.start(appid=app_id, secret=secret)
        except Exception as e:
            print(f"[QQ Channel] Bot 连接错误: {e}")
        print("[QQ Channel] 5 秒后尝试重连...")
        await asyncio.sleep(5)


async def _qq_sender(client, chat_type_cache: dict):
    """
    发送消息到 QQ 从 CHANNEL_QQ_SEND_QUEUE 取消息，通过 QQ API 发送
    """
    while True:
        try:
            # 从发送队列取消息 (channel_id, message)
            channel_id, msg = await CHANNEL_QQ_SEND_QUEUE.get()

            # 解析 chat_id
            if not channel_id.startswith("qq_"):
                print(f"[QQ Channel] 无效的 channel_id: {channel_id}")
                continue

            chat_id = channel_id[3:]  # 去掉 "qq_" 前缀

            # 从缓存获取消息类型
            # QQ群组的group_openid通常比用户openid长
            if channel_id in chat_type_cache:
                is_group = chat_type_cache[channel_id]
            else:
                # 启发式推断：长度>30通常是群组
                is_group = len(chat_id) > 30
                print(f"[QQ Channel] 未找到缓存，推断 {channel_id} 为 {'群组' if is_group else '私聊'}")

            try:
                if is_group:
                    await client.api.post_group_message(
                        group_openid=chat_id,
                        content=msg,
                        msg_type=0,
                    )
                    print(f"[QQ Channel] 已发送到群组 {chat_id[:20]}...: {msg[:50]}")
                else:
                    await client.api.post_c2c_message(
                        openid=chat_id,
                        content=msg,
                        msg_type=0,
                    )
                    print(f"[QQ Channel] 已发送到用户 {chat_id[:20]}...: {msg[:50]}")
            except Exception as e:
                print(f"[QQ Channel] 发送失败: {e}")

        except Exception as e:
            print(f"[QQ Channel] 发送协程异常: {e}")
            await asyncio.sleep(1)
