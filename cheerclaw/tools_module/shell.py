#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   shell.py
@Author  :   zemin
@Desc    :   shell命令执行工具
'''

import asyncio
import os
import re
import signal
import sys
from pathlib import Path
from typing import Any
from loguru import logger
from cheerclaw.tools_module.base import Tool


class ExecTool(Tool):

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",             # rm -r, rm -rf, rm -fr
            r"\bdel\s+/[fq]\b",                 # del /f, del /q
            r"\brmdir\s+/s\b",                  # rmdir /s
            r"(?:^|[;&|]\s*)format\b",          # format (磁盘格式化)
            r"\b(mkfs|diskpart)\b",             # 风险直接操作磁盘硬件
            r"\bdd\s+if=",                      # 风险底层无保护操作，无任何警告，秒级破坏磁盘
            r">\s*/dev/sd",                     # 直接篡改磁盘底层数据，破坏系统分区
            r"\b(shutdown|reboot|poweroff)\b",  # 系统电源操作
            r":\(\)\s*\{.*\};\s*:",             #  fork 炸弹
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append

    @property
    def name(self) -> str:
        return "exec"

    _MAX_TIMEOUT = 600
    _MAX_OUTPUT = 10_000

    @property
    def description(self) -> str:
        return "当需要执行 shell 命令时使用。执行 shell 命令并返回输出。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令",
                },
                "working_dir": {
                    "type": "string",
                    "description": "命令执行的可选工作目录",
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "超时时间（秒）。对于长时间运行的命令如编译或安装可增大此值 "
                        "（默认 60，最大 600）。"
                    ),
                    "minimum": 1,
                    "maximum": 600,
                },
            },
            "required": ["command"],
        }

    async def execute(
        self, command: str, working_dir: str | None = None,
        timeout: int | None = None, **kwargs: Any,
    ) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        effective_timeout = min(timeout or self.timeout, self._MAX_TIMEOUT)

        env = os.environ.copy()
        if self.path_append:
            env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                # 防止孤儿进程
                if sys.platform == "win32":
                    # Windows: 使用 taskkill 杀死进程树
                    os.system(f'taskkill /F /T /PID {process.pid} 2>nul')
                else:
                    # POSIX: 向进程组发送 SIGKILL
                    try:
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # 进程已退出

                # 等待进程退出
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass

                return f"错误: 命令超时（{effective_timeout} 秒）"

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"标准错误输出:\n{stderr_text}")

            output_parts.append(f"退出码: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(无输出)"

            # 头部 + 尾部截断，保留输出的开头和结尾
            max_len = self._MAX_OUTPUT
            if len(result) > max_len:
                half = max_len // 2
                result = (
                    result[:half]
                    + f"\n\n... ({len(result) - max_len:,} 个字符已截断) ...\n\n"
                    + result[-half:]
                )

            return result

        except Exception as e:
            return f"执行命令时出错: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "错误: 命令被安全防护拦截（检测到危险模式）！禁止使用这种危险命令！"

        # 有主动定义的操作指令白名单
        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "错误: 命令被安全防护拦截（不在允许的命令白名单列表中）"

        # 更加严格的模式，只允许在当前目录下的操作
        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "错误: 命令被安全防护拦截（检测到路径遍历）！禁止使用这种危险命令！"

            cwd_path = Path(cwd).resolve()

            for raw in self._extract_absolute_paths(cmd):
                try:
                    expanded = os.path.expandvars(raw.strip())
                    p = Path(expanded).expanduser().resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "错误: 命令被安全防护拦截（路径超出工作目录）"

        return None

    @staticmethod
    def _extract_absolute_paths(command: str) -> list[str]:
        win_paths = re.findall(r"[A-Za-z]:\\[^\s\"'|><;]+", command)   # Windows: C:\...
        posix_paths = re.findall(r"(?:^|[\s|>'\"])(/[^\s\"'>;|<]+)", command) # POSIX: /绝对路径
        home_paths = re.findall(r"(?:^|[\s|>'\"])(~[^\s\"'>;|<]*)", command) # POSIX/Windows 主目录快捷方式: ~
        return win_paths + posix_paths + home_paths
