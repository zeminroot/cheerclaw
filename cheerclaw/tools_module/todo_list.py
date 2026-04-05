#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   todo_list.py
@Author  :   zemin
@Desc    :   使用todolist增强plan and execute作用范围
'''

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from cheerclaw.tools_module.base import Tool, ToolResult


class TodoListManager:

    def __init__(self):
        pass

    def _get_todo_dir(self, workspace: Path) -> Path:
        todo_dir = workspace / "todo_list"
        todo_dir.mkdir(parents=True, exist_ok=True)
        return todo_dir

    def _get_todo_file(self, workspace: Path) -> Path:
        return self._get_todo_dir(workspace) / "todos.jsonl"

    def _generate_task_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"todo_{timestamp}_{unique_id}"

    def get_active_todo(self, workspace: Path) -> Optional[dict]:
        latest_todo = self._get_latest_todo(workspace)
        if latest_todo and latest_todo.get("status") == "active":
            return latest_todo
        return None

    def _get_latest_todo(self, workspace: Path) -> Optional[dict]:
        todo_file = self._get_todo_file(workspace)
        if not todo_file.exists():
            return None

        latest_todo = None
        try:
            with open(todo_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        todo = json.loads(line)
                        if latest_todo is None or todo.get("updated_at", "") > latest_todo.get("updated_at", ""):
                            latest_todo = todo
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return None

        return latest_todo

    def has_active_todo(self, workspace: Path) -> bool:
        return self.get_active_todo(workspace) is not None

    def save_todo(self, workspace: Path, todo: dict) -> dict:
        todo_file = self._get_todo_file(workspace)

        # 更新时间戳
        todo["updated_at"] = datetime.now().isoformat()
        if "created_at" not in todo:
            todo["created_at"] = todo["updated_at"]

        # 追加写入文件
        with open(todo_file, "a", encoding="utf-8") as f:
            json_line = json.dumps(todo, ensure_ascii=False)
            f.write(json_line + "\n")

        return todo

    def create_todo(self, workspace: Path, title: str, items: list) -> dict:
        task_id = self._generate_task_id()

        new_todo = {
            "task_id": task_id,
            "title": title,
            "items": items,
            "status": "active"
        }

        return self.save_todo(workspace, new_todo)

    def update_todo(self, workspace: Path, title: Optional[str] = None,
                    items: Optional[list] = None, status: Optional[str] = None) -> Optional[dict]:
        active_todo = self.get_active_todo(workspace)
        if not active_todo:
            return None

        updated_todo = dict(active_todo)

        if title is not None:
            updated_todo["title"] = title

        if items is not None:
            # 合并 items：用新传入的 items 更新对应 idx 的任务
            existing_items = updated_todo.get("items", [])
            existing_items_map = {item["idx"]: item for item in existing_items}

            for new_item in items:
                idx = new_item.get("idx")
                if idx in existing_items_map:
                    # 更新现有任务
                    existing_items_map[idx].update(new_item)
                else:
                    # 新增任务
                    existing_items_map[idx] = new_item

            # 按 idx 排序并保持原有顺序
            updated_todo["items"] = sorted(existing_items_map.values(), key=lambda x: x["idx"])

            # 如果所有子任务都已完成，自动将 todo list 标记为已完成
            all_items = updated_todo["items"]
            if all_items and all(item.get("status") == "completed" for item in all_items):
                updated_todo["status"] = "completed"

        if status is not None:
            updated_todo["status"] = status

        return self.save_todo(workspace, updated_todo)

    def complete_todo(self, workspace: Path) -> Optional[dict]:
        return self.update_todo(workspace, status="completed")

    def cancel_todo(self, workspace: Path) -> Optional[dict]:
        return self.update_todo(workspace, status="cancelled")

    def render(self, todo: Optional[dict]) -> str:
        if not todo:
            return "当前没有活跃的任务清单"

        lines = []
        lines.append(f"📋 任务: {todo.get('title', '未命名')}")
        lines.append(f"状态: {todo.get('status', 'unknown')}")
        lines.append("")

        items = todo.get("items", [])
        if not items:
            lines.append("（暂无子任务）")
        else:
            for item in items:
                status = item.get("status", "pending")
                marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(status, "[ ]")
                idx = item.get("idx", "?")
                desc = item.get("desc", "")
                lines.append(f"{marker} #{idx}: {desc}")
                lines.append("")  # 空行分隔

            done = sum(1 for item in items if item.get("status") == "completed")
            lines.append(f"\n({done}/{len(items)} 已完成)")

        return "\n".join(lines)


class UpdateTodoTool(Tool):
    def __init__(self, manager: TodoListManager):
        self.manager = manager

    @property
    def name(self) -> str:
        return "update_todo"

    @property
    def description(self) -> str:
        return """创建/更新/完成/取消任务清单，用于跟踪多步骤任务的进度。

使用场景:
- 任务需要3个或以上步骤完成时创建清单
- 每完成一个子任务时更新清单状态
- 任务完成或取消时更新最终状态

使用方法:
1. 创建清单: 传入 title（主任务标题）和 items（子任务列表），系统会自动创建新清单
2. 更新进度: 传入 items 更新子任务状态，系统会更新当前活跃清单
3. 完成清单: 传入 status="completed"
4. 取消清单: 传入 status="cancelled"

限制:
- 已有活跃清单时不能再创建新清单（传入title会报错）
- 没有活跃清单时，必须传入 title 和 items
- 子任务列表最多10项

注意:
- 同一时刻只能有一个进行中的子任务（status="in_progress"）
- 更新时只需要传入变化的字段

示例:
创建: {"title": "修复登录bug", "items": [{"idx": 1, "desc": "定位问题", "status": "pending"}, {"idx": 2, "desc": "修改代码", "status": "pending"}]}
更新: {"items": [{"idx": 1, "desc": "定位问题", "status": "completed"}, {"idx": 2, "desc": "修改代码", "status": "in_progress"}]}
完成: {"status": "completed"}
取消: {"status": "cancelled"}
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "主任务标题。创建新清单时必填，更新时不需要传入。",
                },
                "items": {
                    "type": "array",
                    "description": "子任务列表。创建时必填，更新时必填。每项包含idx/desc/status。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "idx": {"type": "integer", "description": "子任务序号（1,2,3...）"},
                            "desc": {"type": "string", "description": "子任务描述"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "子任务状态"
                            }
                        },
                        "required": ["idx", "desc", "status"]
                    }
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "completed", "cancelled"],
                    "description": "整体状态。active=进行中，completed=已完成，cancelled=已取消。",
                }
            },
            "required": []
        }

    async def execute(
        self,
        title: Optional[str] = None,
        items: Optional[list] = None,
        status: Optional[str] = None,
        **kwargs
    ) -> str:
        # 获取 workspace
        workspace = kwargs.get("channel_workspace")
        if not workspace:
            return "错误: 无法获取 workspace 路径"

        workspace = Path(workspace)

        # 检查是否有活跃清单
        has_active = self.manager.has_active_todo(workspace)

        # 验证 items 格式
        if items is not None:
            valid, error = self._validate_items(items)
            if not valid:
                return f"错误: {error}"

        if not has_active:
            # 没有活跃清单，创建新清单
            if not title:
                return "错误: 没有活跃的任务清单，创建新清单时必须提供 title"

            if not items:
                return "错误: 创建清单时必须提供 items"

            # 创建新清单
            new_todo = self.manager.create_todo(workspace, title, items)

            result = f"✅ 已创建任务清单\n\n{self.manager.render(new_todo)}"
            return result

        else:
            # 有活跃清单，更新
            active_todo = self.manager.get_active_todo(workspace)

            if title is not None and title != active_todo.get("title"):
                return (
                    f"❌ 创建失败: 已有活跃的任务清单\n"
                    f"当前任务: {active_todo.get('title', '未命名')}\n"
                    f"当前活跃的任务清单:\n{self.manager.render(active_todo)}\n"
                    f"请先完成或取消当前任务后再创建新清单。"
                )

            # 更新现有清单
            updated_todo = self.manager.update_todo(
                workspace=workspace,
                items=items,
                status=status
            )

            if not updated_todo:
                return "错误: 更新清单失败，无法获取当前活跃清单"

            # 构建结果消息
            if status == "completed":
                result_prefix = "✅ 任务清单已完成"
            elif status == "cancelled":
                result_prefix = "🚫 任务清单已取消"
            else:
                result_prefix = "✅ 已更新任务清单"

            result = f"{result_prefix}\n\n{self.manager.render(updated_todo)}"
            return result

    def _validate_items(self, items: list) -> tuple[bool, str]:
        if not isinstance(items, list):
            return False, "items 必须是数组"

        if len(items) > 20:
            return False, "最多允许20个子任务"

        in_progress_count = 0
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                return False, f"第{i+1}项必须是对象"

            if "idx" not in item or "desc" not in item or "status" not in item:
                return False, f"第{i+1}项缺少必需字段(idx/desc/status)"

            if item.get("status") == "in_progress":
                in_progress_count += 1
                if in_progress_count > 1:
                    return False, "同一时刻只能有一个进行中的子任务"

        return True, ""
