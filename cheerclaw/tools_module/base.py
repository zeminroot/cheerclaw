#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   base.py
@Author  :   zemin
@Desc    :   工具基类
'''

from abc import ABC, abstractmethod
from typing import Any, Optional


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，必须是唯一的
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述
        描述工具的功能和使用场景
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """工具参数定义（JSON Schema格式）"""
        pass

    @property
    def required_env_vars(self) -> list[str]:
        """需要的环境变量列表"""
        return []

    @property
    def required_packages(self) -> list[str]:
        """需要的 Python 包列表"""
        return []

    @property
    def is_async(self) -> bool:
        """工具是否为异步执行"""
        return True

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass

    def get_schema(self) -> dict:
        """获取工具的 OpenAI Function Calling 格式定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def get_info(self) -> dict:
        """获取工具的详细信息"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "required_env_vars": self.required_env_vars,
            "required_packages": self.required_packages,
            "is_async": self.is_async,
        }

    def validate_params(self, params: dict) -> tuple[bool, Optional[str]]:
        """验证参数是否有效"""
        required = self.parameters.get("required", [])
        for param in required:
            if param not in params:
                return False, f"缺少必填参数: {param}"
        return True, None

    def __repr__(self) -> str:
        return f"Tool(name='{self.name}', desc='{self.description[:30]}...')"

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"


class ToolResult:

    def __init__(self, tool_name: str, success: bool, data: Any = None, error: Optional[str] = None):
        self.tool_name = tool_name
        self.success = success
        self.data = data
        self.error = error

    @classmethod
    def success(cls, tool_name: str, data: Any) -> "ToolResult":
        """创建成功的工具结果"""
        return cls(tool_name=tool_name, success=True, data=data, error=None)

    @classmethod
    def error(cls, tool_name: str, error: str) -> "ToolResult":
        """创建失败的工具结果"""
        return cls(tool_name=tool_name, success=False, data=None, error=error)

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }

    def __repr__(self) -> str:
        if self.success:
            return f"ToolResult({self.tool_name}, success, data={str(self.data)[:50]}...)"
        else:
            return f"ToolResult({self.tool_name}, error={self.error})"

    def __str__(self) -> str:
        if self.success:
            return f"工具执行成功 ✓ {self.tool_name}: {self.data}"
        else:
            return f"工具执行失败 ✗ {self.tool_name}: {self.error}"


