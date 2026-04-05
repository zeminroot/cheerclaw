#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   read_skill.py
@Author  :   zemin
@Desc    :   读取完整的skill
'''

from cheerclaw.tools_module.base import Tool
from cheerclaw.skills_module import SkillLoader


class ReadSkillTool(Tool):
    def __init__(self, skill_loader: SkillLoader):
        self.skill_loader = skill_loader

    @property
    def name(self) -> str:
        return "read_skill"

    @property
    def description(self) -> str:
        return """读取技能的完整内容。当需要使用某个技能时调用此工具。参考技能中的指南来完成任务。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "技能名称，例如 'code'",
                },
            },
            "required": ["name"],
        }

    async def execute(self, name: str) -> str:
        content = self.skill_loader.load_skill(name)
        if content:
            return f"# 技能: {name}\n\n{content}"
        return f"错误：找不到技能 '{name}'"
