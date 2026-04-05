#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   openai_client.py
@Author  :   zemin
@Desc    :   异步客户端
'''


from typing import Optional
from openai import AsyncOpenAI
from cheerclaw.config.config_loader import load_config
from cheerclaw.config.config_schema import Config


def create_openai_client(config: Optional[Config] = None) -> AsyncOpenAI:
    """
    从配置创建 AsyncOpenAI 客户端
    """
    cfg = config or load_config()
    p = cfg.provider

    if not p.api_key:
        raise ValueError("API Key 不能为空")

    kwargs = {"api_key": p.api_key, "timeout": p.timeout}
    if p.api_base:
        kwargs["base_url"] = p.api_base

    return AsyncOpenAI(**kwargs)



