#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   cron_channel.py
@Author  :   zemin
@Desc    :   定时任务调度器通道
'''

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict

# 全局输入队列引用（由主模块注入）
_global_in_queue = None
_global_cheerclaw_dir = None


def set_global_in_queue(queue: asyncio.Queue):
    """
    设置全局输入队列
    """
    global _global_in_queue
    _global_in_queue = queue


def set_cheerclaw_dir(cheerclaw_dir: Path):
    """
    设置配置目录
    """
    global _global_cheerclaw_dir
    _global_cheerclaw_dir = cheerclaw_dir


async def cron_scheduler_task(
    global_in_queue: asyncio.Queue = None,
    cheerclaw_dir: Path = None
):
    """
    定时任务调度器后台协程
    每分钟检查一次所有定时任务，触发到期的任务
    global_in_queue: 全局输入队列，用于发送定时任务消息
    cheerclaw_dir: CheerClaw 配置目录路径
    """
    if global_in_queue:
        set_global_in_queue(global_in_queue)

    if cheerclaw_dir:
        set_cheerclaw_dir(cheerclaw_dir)

    if not _global_in_queue:
        raise RuntimeError("全局输入队列未设置")

    if not _global_cheerclaw_dir:
        raise RuntimeError("配置目录未设置")

    from cheerclaw.tools_module.cron_task import CronTaskManager, CronExpressionParser

    cron_manager = CronTaskManager(clawspace=_global_cheerclaw_dir)

    # 记录已触发过的任务，避免同一分钟重复触发，格式: {task_filepath: last_triggered_minute}
    triggered_tasks: Dict[str, str] = {}

    while True:
        try:
            now = datetime.now()
            current_minute = now.strftime("%Y-%m-%d %H:%M")
            # 加载所有定时任务（从 clawspace/cron/ 目录）
            tasks = cron_manager.load_all_tasks()

            for task in tasks:
                if not task.get("enabled", True):
                    continue

                filepath = task.get("_filepath")
                if not filepath:
                    continue

                # 检查是否已经在这个分钟触发过
                if triggered_tasks.get(filepath) == current_minute:
                    continue

                # 检查 cron 表达式是否匹配当前时间
                cron_expr = task.get("cron_expression", "")
                if CronExpressionParser.match(cron_expr, now):
                    # 触发任务
                    source_channel_id = task.get("source_channel_id", "unknown")
                    task_prompt = task.get("task_prompt", "")

                    if task_prompt:
                        print(f"[CronScheduler] 触发任务: {task.get('description', '未命名')} -> {source_channel_id}")

                        # 发送消息给主 Agent (channel_id, channel_source, channel_describe, message)
                        await _global_in_queue.put((source_channel_id, "cron", "定时任务调度", f"[触发已存在的定时任务] {task_prompt}"))

                        # 更新任务执行记录
                        cron_manager.update_task_execution(task)

                        # 记录已触发
                        triggered_tasks[filepath] = current_minute

            # 每分钟检查一次
            await asyncio.sleep(60)

        except Exception as e:
            print(f"[CronScheduler] 调度器异常: {e}")
            await asyncio.sleep(60)  
