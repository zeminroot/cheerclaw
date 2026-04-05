#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   filesystem.py
@Author  :   zemin
@Desc    :   
- read_file: 读取文件内容
- write_file: 写入文件内容
- list_dir: 列出目录内容
- edit_file: 编辑文件内容
'''

import os
from pathlib import Path
from typing import Optional

from cheerclaw.tools_module.base import Tool, ToolResult


class ReadFileTool(Tool):

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return """读取文件内容。用于查看文件的内容。

适用场景：
- 查看代码文件
- 阅读文档
- 检查配置文件
- 分析日志文件

安全说明：
- 只能读取存在的文件
- 不能读取二进制文件（会提示编码错误）
- 支持相对路径和绝对路径"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对或绝对）",
                },
                "limit": {
                    "type": "integer",
                    "description": "读取的最大行数（可选，默认读取全部）",
                },
                "offset": {
                    "type": "integer",
                    "description": "从第几行开始读取（可选，从1开始计数）",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, limit: Optional[int] = None, offset: Optional[int] = None) -> str:
        try:
            file_path = Path(path)

            # 检查文件是否存在
            if not file_path.exists():
                return f"错误：文件不存在: {path}"

            # 检查是否为文件
            if not file_path.is_file():
                return f"错误：路径不是文件: {path}"

            # 读取文件
            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")

            # 处理 offset
            if offset and offset > 0:
                lines = lines[offset - 1:]

            # 处理 limit
            if limit and limit > 0:
                lines = lines[:limit]

            result = "\n".join(lines)

            # 添加文件信息
            info = f"# 文件: {path}\n"
            if offset:
                info += f"# 行数: {offset}-{offset + len(lines) - 1}\n"
            else:
                info += f"# 总行数: {len(lines)}\n"
            info += "# " + "=" * 40 + "\n\n"

            return info + result

        except UnicodeDecodeError:
            return f"错误：文件不是文本文件或编码不支持: {path}"
        except Exception as e:
            return f"读取文件错误: {str(e)}"


class WriteFileTool(Tool):

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return """写入文件内容。用于创建新文件或覆盖现有文件。

适用场景：
- 创建新文件
- 生成代码文件
- 保存分析结果
- 写入配置文件

安全说明：
- 会覆盖已存在的文件（请谨慎使用）
- 自动创建父目录"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对或绝对）",
                },
                "content": {
                    "type": "string",
                    "description": "文件内容",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> str:
        try:
            file_path = Path(path)

            # 创建父目录
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 检查是否为覆盖
            is_overwrite = file_path.exists()

            # 写入文件
            file_path.write_text(content, encoding="utf-8")

            if is_overwrite:
                return f"成功覆盖文件: {path}"
            else:
                return f"成功创建文件: {path}"

        except Exception as e:
            return f"写入文件错误: {str(e)}"


class ListDirTool(Tool):

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return """列出目录内容。用于查看文件夹中的文件和子目录。

适用场景：
- 查看项目结构
- 浏览文件系统
- 确认文件是否存在

安全说明：
- 只能列出存在的目录
- 显示文件类型标记（/ 表示目录，@ 表示链接）"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径（相对或绝对，默认为当前目录）",
                },
            },
            "required": [],
        }

    async def execute(self, path: str = ".") -> str:
        try:
            dir_path = Path(path)

            # 检查目录是否存在
            if not dir_path.exists():
                return f"错误：路径不存在: {path}"

            if not dir_path.is_dir():
                return f"错误：路径不是目录: {path}"

            # 列出内容
            items = []
            for item in sorted(dir_path.iterdir()):
                # 标记类型
                marker = ""
                if item.is_dir():
                    marker = "/"
                elif item.is_symlink():
                    marker = "@"

                items.append(f"{item.name}{marker}")

            result = "\n".join(items)
            return f"目录: {path}\n{result}"

        except Exception as e:
            return f"列出目录错误: {str(e)}"


class EditFileTool(Tool):

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return """编辑文件内容。查找并替换文件中的指定文本。

适用场景：
- 修改代码中的特定行
- 更新配置文件
- 批量替换文本

安全说明：
- 必须完全匹配 old_string
- 如果找不到匹配内容会报错
- 会先创建备份文件（.bak）"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径",
                },
                "old_string": {
                    "type": "string",
                    "description": "要替换的旧文本",
                },
                "new_string": {
                    "type": "string",
                    "description": "替换为的新文本",
                },
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, path: str, old_string: str, new_string: str) -> str:
        try:
            file_path = Path(path)

            # 检查文件是否存在
            if not file_path.exists():
                return f"错误：文件不存在: {path}"

            # 读取原内容
            content = file_path.read_text(encoding="utf-8")

            # 检查是否包含旧文本
            if old_string not in content:
                return f"错误：文件中没有找到要替换的文本: {old_string[:50]}..."

            # 创建备份
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            backup_path.write_text(content, encoding="utf-8")

            # 执行替换
            new_content = content.replace(old_string, new_string, 1)

            # 写回文件
            file_path.write_text(new_content, encoding="utf-8")

            return f"成功编辑文件: {path}\n已创建备份: {backup_path}"

        except Exception as e:
            return f"编辑文件错误: {str(e)}"
