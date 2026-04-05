#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   calculator.py
@Author  :   zemin
@Desc    :   数学计算
'''

from cheerclaw.tools_module.base import Tool


class CalculatorTool(Tool):

    @property
    def name(self) -> str:
        return "calculate"

    @property
    def description(self) -> str:
        return """执行数学计算。当用户需要计算时使用此工具。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如 '2 + 2'、'10 * 5'、'sqrt(16)'",
                },
            },
            "required": ["expression"],
        }

    async def execute(self, expression: str) -> str:
        try:
            allowed = set("0123456789+-*/(). ")
            if not all(c in allowed for c in expression):
                return "错误：表达式包含非法字符"

            result = eval(expression, {"__builtins__": {}}, {})
            return f"{expression} = {result}"
        except Exception as e:
            return f"计算错误: {str(e)}"
