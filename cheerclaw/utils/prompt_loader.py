#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   prompt_loader.py
@Author  :   zemin
@Desc    :   提示词加载器
'''



import re
from pathlib import Path
from typing import Any


def load_prompt(template_name: str, **variables: Any) -> str:
    """
    加载提示词模板并替换变量

    参数：
        template_name: 模板文件名（不含路径，从 prompts 目录查找）
        **variables: 要替换的变量，如 skills_summary="xxx"

    返回：
        替换变量后的提示词字符串
    """
    # 优先从 agent/prompts 目录查找模板文件
    search_paths = [
        Path(__file__).parent.parent / "context" / "prompts",
        Path.cwd() / "agent" / "prompts",
    ]

    template_path = None
    for path in search_paths:
        candidate = path / template_name
        if candidate.exists():
            template_path = candidate
            break

    if not template_path:
        raise FileNotFoundError(f"找不到提示词模板: {template_name}")

    content = template_path.read_text(encoding="utf-8")

    # 替换变量 
    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        content = content.replace(placeholder, str(value))

    # 检查是否有未替换的占位符
    remaining = re.findall(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}", content)
    if remaining:
        # 未替换的置为空字符串
        for key in remaining:
            content = content.replace(f"{{{{{key}}}}}", "")

    return content


def load_prompt_from_path(file_path: Path | str, **variables: Any) -> str:
    """
    从指定路径加载提示词模板

    参数：
        file_path: 模板文件路径
        **variables: 要替换的变量

    返回：
        替换变量后的提示词字符串
    """
    template_path = Path(file_path)

    if not template_path.exists():
        raise FileNotFoundError(f"找不到提示词模板: {template_path}")

    content = template_path.read_text(encoding="utf-8")

    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        content = content.replace(placeholder, str(value))

    return content


