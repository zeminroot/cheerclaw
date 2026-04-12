#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   feishu_channel.py
@Author  :   zemin
@Desc    :   飞书Channel 使用WebSocket长连接
1. 在飞书开放平台创建企业自建应用
2. 开启机器人能力
3. 订阅事件
4. 权限管理
5. 发布版本，获取App ID和App Secret
'''

import asyncio
import json
import threading
from collections import OrderedDict
from typing import Optional
from loguru import logger

# Feishu Channel专用的发送队列接，收输出消息，发送给飞书
CHANNEL_FEISHU_SEND_QUEUE = asyncio.Queue()

# 全局输入队列（由主模块注入）
_global_in_queue = None

# Channel标识，注册到 ChannelInfoManager
CHANNEL_SOURCE = "feishu"
CHANNEL_DESCRIBE = "飞书机器人通道"

FEISHU_AVAILABLE = False
try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    FEISHU_AVAILABLE = True
except ImportError:
    lark = None
    logger.warning("[Feishu Channel] lark_oapi 未安装，飞书功能不可用。使用pip install lark-oapi")


def set_global_in_queue(queue: asyncio.Queue):
    """
    设置全局输入队列
    """
    global _global_in_queue
    _global_in_queue = queue


class FeishuMessageHandler:

    def __init__(self, global_in_queue: asyncio.Queue):
        self.global_in_queue = global_in_queue
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # 去重缓存
        self._chat_type_cache: dict[str, str] = {}  # chat_id -> chat_type 缓存
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """
        设置事件循环
        """
        self._loop = loop

    def _is_duplicate(self, message_id: str) -> bool:
        """
        检查消息是否重复
        """
        if message_id in self._processed_message_ids:
            return True
        self._processed_message_ids[message_id] = None
        # 限制缓存大小
        while len(self._processed_message_ids) > 1000:
            self._processed_message_ids.popitem(last=False)
        return False

    def _generate_channel_id(self, chat_id: str, chat_type: str, sender_id: str) -> str:
        """
        生成 CheerClaw格式的channel_id
        格式: feishu_{chat_type}_{chat_id}
        私聊: feishu_p2p_{open_id}
        群聊: feishu_group_{chat_id}
        """
        if chat_type == "p2p":
            return f"feishu_p2p_{sender_id}"
        else:
            return f"feishu_group_{chat_id}"

    def _extract_text_content(self, msg_type: str, content: str) -> str:
        """
        从飞书消息内容中提取纯文本
        """
        if msg_type == "text":
            try:
                data = json.loads(content) if content else {}
                return data.get("text", "")
            except json.JSONDecodeError:
                return content

        elif msg_type == "post":
            # 富文本消息，简单提取文本
            try:
                data = json.loads(content) if content else {}
                # 提取 zh_cn 内容
                zh_cn = data.get("zh_cn", data.get("post", {}).get("zh_cn", {}))
                paragraphs = zh_cn.get("content", [])
                texts = []
                for row in paragraphs:
                    if isinstance(row, list):
                        for item in row:
                            if isinstance(item, dict):
                                tag = item.get("tag")
                                if tag in ("text", "a"):
                                    texts.append(item.get("text", ""))
                                elif tag == "at":
                                    texts.append(f"@{item.get('user_name', 'user')}")
                return " ".join(texts)
            except (json.JSONDecodeError, AttributeError):
                return f"[{msg_type} message]"

        else:
            # 其他类型消息
            return f"[{msg_type} message]"

    def handle_message_sync(self, data) -> None:
        """
        同步处理飞书消息，从WebSocket线程调用
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._handle_message(data), self._loop)

    async def _handle_message(self, data) -> None:
        """
        异步处理飞书消息
        """
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # 去重检查
            message_id = message.message_id
            if self._is_duplicate(message_id):
                return

            # 跳过机器人消息
            if sender.sender_type == "bot":
                return

            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type  # "p2p" 或 "group"
            msg_type = message.message_type

            if msg_type not in ("text", "post"):
                logger.debug(f"[Feishu Channel] 跳过非文本消息类型: {msg_type}")
                return

            # 提取文本内容
            content = self._extract_text_content(msg_type, message.content or "")
            if not content.strip():
                return

            # 生成 channel_id
            channel_id = self._generate_channel_id(chat_id, chat_type, sender_id)

            # 缓存 chat 类型，用于发送时判断
            self._chat_type_cache[channel_id] = chat_type

            # 构建 channel_describe
            if chat_type == "p2p":
                describe = f"飞书私聊 {sender_id[:16]}..."
            else:
                describe = f"飞书群组 {chat_id[:16]}..."

            # 推送到全局输入队列
            if self.global_in_queue:
                await self.global_in_queue.put((channel_id, CHANNEL_SOURCE, describe, content.strip()))
                logger.info(f"[Feishu Channel] 收到消息 from {channel_id}: {content[:50]}...")

        except Exception as e:
            logger.error(f"[Feishu Channel] 处理消息异常: {e}")


async def feishu_sender(client, handler: FeishuMessageHandler):
    """
    发送消息到飞书
    从 CHANNEL_FEISHU_SEND_QUEUE 取消息，通过飞书 API 发送
    """
    while True:
        try:
            # 从发送队列取消息 (channel_id, message)
            channel_id, msg = await CHANNEL_FEISHU_SEND_QUEUE.get()

            # 拆解 chat_id 和 chat_type
            if not channel_id.startswith("feishu_"):
                logger.warning(f"[Feishu Channel] 无效的 channel_id: {channel_id}")
                continue

            # 提取 chat_type 和 chat_id 格式: feishu_p2p_{open_id} 或 feishu_group_{chat_id}
            parts = channel_id.split("_", 2)
            if len(parts) < 3:
                logger.warning(f"[Feishu Channel] 无效的 channel_id 格式: {channel_id}")
                continue

            chat_type = parts[1]  # "p2p" 或 "group"
            target_id = parts[2]

            # 构建接收者参数
            if chat_type == "p2p":
                receive_id_type = "open_id"
                receive_id = target_id
            else:
                receive_id_type = "chat_id"
                receive_id = target_id

            # 构建消息内容
            content = json.dumps({"text": msg}, ensure_ascii=False)

            # 发送消息
            try:
                request = CreateMessageRequest.builder() \
                    .receive_id_type(receive_id_type) \
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(receive_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                    ).build()

                response = client.im.v1.message.create(request)

                if response.success():
                    logger.info(f"[Feishu Channel] 消息已发送到 {channel_id}: {msg[:50]}...")
                else:
                    logger.error(f"[Feishu Channel] 发送失败: code={response.code}, msg={response.msg}")

            except Exception as e:
                logger.error(f"[Feishu Channel] 发送异常: {e}")

        except Exception as e:
            logger.error(f"[Feishu Channel] 发送协程异常: {e}")
            await asyncio.sleep(1)


async def feishu_channel(global_in_queue: asyncio.Queue = None, feishu_config=None):
    """
    飞书 Channel 入口
    接收飞书消息 -> 生成 channel_id -> 推送到 GLOBAL_IN_QUEUE
    从 CHANNEL_FEISHU_SEND_QUEUE 取消息 -> 发送到飞书
    global_in_queue: 全局输入队列
    feishu_config: 飞书配置，包含 app_id 和 app_secret
    """
    if global_in_queue:
        set_global_in_queue(global_in_queue)

    if not _global_in_queue:
        raise RuntimeError("[Feishu Channel] 全局输入队列未设置")

    if not FEISHU_AVAILABLE:
        logger.warning("[Feishu Channel] lark_oapi 未安装，飞书功能未启动。使用 pip install lark-oapi")
        # 保持存活，不退出
        while True:
            await asyncio.sleep(60)

    # 获取配置
    app_id = getattr(feishu_config, 'app_id', '') if feishu_config else ''
    app_secret = getattr(feishu_config, 'app_secret', '') if feishu_config else ''

    if not app_id or not app_secret:
        logger.warning("[Feishu Channel] 飞书配置未设置（config.json 中缺少 feishu.app_id 或 feishu.app_secret）")
        logger.warning("[Feishu Channel] 请在 config.json 中添加:")
        logger.warning('  "feishu": {"app_id": "your_app_id", "app_secret": "your_app_secret"}')
        # 保持存活，不退出
        while True:
            await asyncio.sleep(60)

    # 创建消息处理器
    handler = FeishuMessageHandler(_global_in_queue)

    # 创建飞书客户端
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    # 构建事件处理器
    event_handler = lark.EventDispatcherHandler.builder(
        "",  # encrypt_key
        "",  # verification_token
    ).register_p2_im_message_receive_v1(
        handler.handle_message_sync
    ).build()

    # 创建 WebSocket 客户端
    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO
    )

    # 启动WebSocket的线程函数
    def run_ws():
        import lark_oapi.ws.client as _lark_ws_client
        import time

        # 创建独立的事件循环
        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        _lark_ws_client.loop = ws_loop

        try:
            while True:
                try:
                    ws_client.start()
                except Exception as e:
                    logger.warning(f"[Feishu Channel] WebSocket 错误: {e}")
                time.sleep(5)  # 5秒后重连
        finally:
            ws_loop.close()

    # 设置事件循环引用
    handler.set_loop(asyncio.get_running_loop())

    # 在后台线程启动 WebSocket
    ws_thread = threading.Thread(target=run_ws, daemon=True)
    ws_thread.start()

    print("[Feishu Channel] 飞书机器人正在启动...")
    print(f"[Feishu Channel] App ID: {app_id[:8]}...")
    print("[Feishu Channel] 使用 WebSocket 长连接")
    print("[Feishu Channel] 等待连接...")

    # 启动发送协程（主协程）
    await feishu_sender(client, handler)
