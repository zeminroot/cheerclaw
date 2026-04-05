#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   diff_helper.py
@Author  :   zemin
@Desc    :   None
'''

import difflib
from dataclasses import dataclass
from typing import List


@dataclass
class DiffResult:
    """差异对比结果"""
    diff_lines: List[str]


def compare_strings(old_string: str, new_string: str, context_lines: int = 3) -> DiffResult:
    """对比两个字符串，生成差异结果"""
    old_lines = old_string.splitlines(keepends=True)
    new_lines = new_string.splitlines(keepends=True)

    if old_lines and not old_lines[-1].endswith('\n'):
        old_lines[-1] += '\n'
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        lineterm='',
        n=context_lines
    )

    return DiffResult(diff_lines=list(diff))


def format_diff(old_content: str, new_content: str, max_lines: int = 50) -> str:
    """生成纯文本格式的 diff 字符串（带行号）
    old_content: 原始内容
    new_content: 新内容
    max_lines: 最大展示行数
    返回: 纯文本格式的 diff 字符串
    """
    if not old_content and not new_content:
        return "（无内容变化）"

    # 纯新增文件
    if not old_content:
        lines = new_content.splitlines()
        formatted_lines = [f"  {'':>4} {'':>4}   | {line}" for line in lines]
        if len(lines) > max_lines:
            return f"（新增文件，共 {len(lines)} 行）\n" + '\n'.join(formatted_lines[:max_lines]) + f"\n... （还有 {len(lines) - max_lines} 行未显示）"
        return '\n'.join(formatted_lines)

    diff_result = compare_strings(old_content, new_content)

    if not diff_result.diff_lines:
        return "（无内容变化）"

    formatted_lines = []
    line_count = 0
    has_more = False
    old_line_num = 1
    new_line_num = 1

    for line in diff_result.diff_lines:
        if line.startswith('---') or line.startswith('+++'):
            continue

        if line_count >= max_lines:
            has_more = True
            continue

        if line.startswith('@@'):
            # 解析 @@ -x,y +a,b @@ 获取起始行号
            import re
            match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', line)
            if match:
                old_line_num = int(match.group(1))
                new_line_num = int(match.group(3))
            continue

        if line.startswith('-'):
            # 删除的行：显示旧行号，新行号为空白
            formatted_lines.append(f"- {old_line_num:>4} {'':>4} | {line[1:]}")
            old_line_num += 1
        elif line.startswith('+'):
            # 新增的行：显示新行号，旧行号为空白
            formatted_lines.append(f"+ {'':>4} {new_line_num:>4} | {line[1:]}")
            new_line_num += 1
        else:
            # 未变更的行：显示双行号
            formatted_lines.append(f"  {old_line_num:>4} {new_line_num:>4} | {line[1:]}")
            old_line_num += 1
            new_line_num += 1

        line_count += 1

    # 添加表头
    header = f"  {'':>4} {'':>4}   |\n"
    result = header + '\n'.join(formatted_lines)
    if has_more:
        result += f"\n... （还有更多内容未显示）"

    return result
