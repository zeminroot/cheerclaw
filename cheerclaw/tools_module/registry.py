#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   registry.py
@Author  :   zemin
@Desc    :   工具注册表
'''

from typing import Optional
import asyncio
from loguru import logger
from cheerclaw.tools_module.base import Tool, ToolResult


class ToolRegistry:

    def __init__(self):
        """
        初始化工具注册表
        包含：注册、注销、查找、获取schema、执行等功能
        """
        self._tools: dict[str, Tool] = {}


    def register(self, tool: Tool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            raise ValueError(f"工具 '{tool.name}' 已存在")

        self._tools[tool.name] = tool
        logger.info(f"[ToolRegistry] 已注册工具: {tool.name}")

    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"[ToolRegistry] 已注销工具: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """获取所有工具名称列表"""
        return list(self._tools.keys())

    def count(self) -> int:
        """获取注册的工具数量"""
        return len(self._tools)


    def get_schemas(self) -> list[dict]:
        """获取所有工具的 OpenAI 格式定义"""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_infos(self) -> dict[str, dict]:
        """获取所有工具的详细信息"""
        return {name: tool.get_info() for name, tool in self._tools.items()}


    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """执行工具
        name: 工具名称
        arguments: 工具参数字典
        返回: ToolResult 执行结果
        """
        # 1. 查找工具
        tool = self.get(name)
        if not tool:
            return ToolResult.error(name, f"工具 '{name}' 不存在")

        # 2. 验证参数
        valid, error = tool.validate_params(arguments)
        if not valid:
            return ToolResult.error(name, f"参数验证失败: {error}")

        # 3. 执行工具
        try:
            if tool.is_async:
                # 异步执行
                result = await tool.execute(**arguments)
            else:
                # 同步执行
                result = tool.execute(**arguments)

            return ToolResult.success(name, result)

        except Exception as e:
            return ToolResult.error(name, f"执行异常: {str(e)}")

    async def execute_many(self, tool_calls: list[dict]) -> list[ToolResult]:
        """并发执行多个工具"""
        tasks = [
            self.execute(tc["name"], tc["arguments"])
            for tc in tool_calls
        ]
        return await asyncio.gather(*tasks)


    def register_many(self, tools: list[Tool]) -> None:
        """批量注册工具"""
        for tool in tools:
            self.register(tool)

    def unregister_all(self) -> None:
        """注销所有工具"""
        self._tools.clear()
        logger.info("[ToolRegistry] 已注销所有工具")


    def get_stats(self) -> dict:
        """获取注册表统计信息"""
        return {
            "total_tools": self.count(),
            "tool_names": self.list_tools(),
        }

    def __repr__(self) -> str:
        """字符串表示"""
        tools = ", ".join(self.list_tools())
        return f"ToolRegistry({self.count()} tools: {tools})"


