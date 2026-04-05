#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   config_schema.py
@Author  :   zemin
@Desc    :   配置
'''

from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class ProviderConfig(BaseModel):
    """
    LLM Provider 配置

    支持任意 OpenAI 兼容的 API
    """
    api_key: str = Field(default="", description="API 密钥")
    api_base: Optional[str] = Field(default=None, description="API 基础地址")
    model: str = Field(default="gpt-3.5-turbo", description="模型名称")
    timeout: int = Field(default=600, ge=10, le=3600, description="API 调用超时时间（秒），默认 600 秒")
    max_completion_tokens: int = Field(default=4096, ge=100, le=32000, description="最大生成 token 数，默认 4096")
    max_context: int = Field(default=100000, ge=1000, le=1000000, description="模型最大上下文窗口长度，默认 100k")
    extra_body: Optional[dict[str, Any]] = Field(default=None, description="额外的请求参数，原样传递给 OpenAI SDK")

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        return v


class AgentConfig(BaseModel):
    """
    Agent 行为配置
    """
    name: str = Field(default="CheerClaw", description="Agent 名称")
    confirm_tools: list[str] = Field(
        default=["edit_file", "write_file"],
        description="需要用户确认的工具列表"
    )
    dangerous_keywords: list[str] = Field(
        default=["rm ", "remove ", "delete ", "del ", "mv ", "move ", "chmod ", "chown", "sudo ", "dd ", "format ", "mkfs"],
        description="exec 工具中需要确认的危险命令关键字"
    )


class QQConfig(BaseModel):
    """
    QQ Bot 配置
    """
    app_id: str = Field(default="", description="QQ Bot App ID")
    secret: str = Field(default="", description="QQ Bot Secret")


class TavilyConfig(BaseModel):
    """
    Tavily 搜索配置
    """
    api_key: str = Field(default="", description="Tavily API Key")


class Config(BaseModel):
    """
    根配置对象 对应 config.json 的结构
    """
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    tavily: TavilyConfig = Field(default_factory=TavilyConfig)

    class Config:
        """Pydantic 配置"""
        populate_by_name = True  # 允许用字段名赋值
        extra = "ignore"  # 忽略未知字段（向后兼容）
