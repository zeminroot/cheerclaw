#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   cron_task.py
@Author  :   zemin
@Desc    :   定时任务管理工具
'''

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Optional
from cheerclaw.tools_module.base import Tool
from croniter import croniter


class CronExpressionParser:

    @staticmethod
    def match(cron_expression: str, dt: datetime = None) -> bool:
        if dt is None:
            dt = datetime.now()

        try:
            # 使用 croniter.match 直接检查当前时间是否匹配
            return croniter.match(cron_expression, dt)
        except Exception:
            return False


class CronTaskManager:

    def __init__(self, clawspace: Path = None):
        if clawspace is None:
            clawspace = Path.home() / ".cheerclaw"
        self.clawspace = Path(clawspace)

    def _get_cron_dir(self) -> Path:
        cron_dir = self.clawspace / "cron"
        cron_dir.mkdir(parents=True, exist_ok=True)
        return cron_dir

    def _generate_task_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))
        return f"cron_{timestamp}_{random_suffix}"

    def create_task(
        self,
        description: str,
        cron_expression: str,
        source_channel_id: str,
        task_prompt: str
    ) -> dict:
        cron_dir = self._get_cron_dir()
        task_id = self._generate_task_id()

        task = {
            "task_id": task_id,
            "description": description,
            "cron_expression": cron_expression,
            "source_channel_id": source_channel_id,
            "task_prompt": task_prompt,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
            "last_executed_at": None,
            "execute_count": 0
        }

        # 文件名: {description}_{task_id}.json
        safe_description = "".join(c if c.isalnum() or c in '_-' else '_' for c in description)
        filename = f"{safe_description}_{task_id}.json"
        filepath = cron_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        return task

    def load_all_tasks(self) -> list[dict]:
        cron_dir = self._get_cron_dir()
        tasks = []

        if not cron_dir.exists():
            return tasks

        for filepath in cron_dir.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    task = json.load(f)
                    task["_filepath"] = str(filepath)  # 记录文件路径用于更新
                    tasks.append(task)
            except (json.JSONDecodeError, IOError):
                continue

        return tasks

    def update_task_execution(self, task: dict) -> bool:
        filepath = task.get("_filepath")
        if not filepath:
            return False

        try:
            task["last_executed_at"] = datetime.now().isoformat()
            task["execute_count"] = task.get("execute_count", 0) + 1

            with open(filepath, "w", encoding="utf-8") as f:
                # 移除内部字段
                save_task = {k: v for k, v in task.items() if not k.startswith("_")}
                json.dump(save_task, f, ensure_ascii=False, indent=2)
            return True
        except IOError:
            return False

    def get_enabled_tasks(self) -> list[dict]:
        all_tasks = self.load_all_tasks()
        return [t for t in all_tasks if t.get("enabled", True)]


class ManageCronTaskTool(Tool):

    def __init__(self, manager: CronTaskManager):
        self.manager = manager

    @property
    def name(self) -> str:
        return "manage_cron_task"

    @property
    def description(self) -> str:
        return """创建定时任务，让系统在指定时间自动执行任务。

使用场景：
- 用户需要定时提醒时、周期性任务时、在特定时间执行任务时

定时任务文件在clawspace目录下 {Path.home() / '.cheerclaw' / 'cron'} 使用 shell 工具查看和删除任务：
- 查看: ls {clawspace}/cron/
- 删除: rm {clawspace}/cron/xxx.json
修改定时任务：先查看并删除原有的定时任务，再创建新的定时任务，或对原json文件直接修改。

示例:
{"description": "早安消息", "cron_expression": "0 6 * * *", "source_channel_id": "qq", "task_prompt": "发送早安消息给xx，祝他有美好的一天"}
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "任务描述，简短明了，用于生成文件名"
                },
                "cron_expression": {
                    "type": "string",
                    "description": "cron 表达式，定义执行时间（如'0 6 * * *'表示每天早上6点）"
                },
                "source_channel_id": {
                    "type": "string",
                    "description": "任务来源 channel ID（如'qq'）"
                },
                "task_prompt": {
                    "type": "string",
                    "description": "任务内容，定时触发时发给主 agent 的内容（只需写任务内容，不需要定时时间信息）"
                }
            },
            "required": ["description", "cron_expression", "source_channel_id", "task_prompt"]
        }

    async def execute(
        self,
        description: str,
        cron_expression: str,
        source_channel_id: str,
        task_prompt: str,
        **kwargs
    ) -> str:
        """
        创建定时任务
        """
        # 验证 cron 表达式格式
        if not self._validate_cron_expression(cron_expression):
            return f"错误: cron 表达式格式不正确 '{cron_expression}'，正确格式为5字段: 分 时 日 月 星期"

        # 创建任务
        task = self.manager.create_task(
            description=description,
            cron_expression=cron_expression,
            source_channel_id=source_channel_id,
            task_prompt=task_prompt
        )

        cron_dir = self.manager.clawspace / "cron"

        return (
            f"✅ 已创建定时任务\n"
            f"\n"
            f"任务ID: {task['task_id']}\n"
            f"描述: {task['description']}\n"
            f"执行时间: {task['cron_expression']}\n"
            f"来源Channel: {task['source_channel_id']}\n"
            f"任务内容: {task['task_prompt']}\n"
            f"\n"
            f"文件保存在: {cron_dir}/\n"
            f"查看任务: ls {cron_dir}/\n"
            f"删除任务: rm {cron_dir}/{task['description']}_{task['task_id']}.json"
        )

    def _validate_cron_expression(self, expr: str) -> bool:
        parts = expr.strip().split()
        if len(parts) != 5:
            return False

        # 简单验证每个字段格式
        for part in parts:
            if not part:
                return False
            # 允许: 数字、*、-、/、,
            if not all(c.isdigit() or c in "*-,/" for c in part):
                return False

        return True
