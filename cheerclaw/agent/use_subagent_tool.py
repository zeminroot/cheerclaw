#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   use_subagent_tool.py
@Author  :   zemin
@Desc    :   调用子Agent工具
'''

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from openai import AsyncOpenAI

from cheerclaw.tools_module.base import Tool
from cheerclaw.agent.sub_agent import SubAgent


class UseSubagentTool(Tool):
    EXCLUDED_TOOLS = {"use_subagent", "update_todo", "send_message", "manage_cron_task"}

    def __init__(
        self,
        config,
        skill_loader,
        tools_schemas: list[dict],
        model: str,
        client: "AsyncOpenAI",
    ):
        """
        初始化UseSubagentTool
        config: 配置对象
        skill_loader: 技能加载器实例
        tools_schemas: 工具定义列表(OpenAI格式)
        model: 模型名称
        client: OpenAI异步客户端
        """
        self.config = config
        self.skill_loader = skill_loader
        self.tools_schemas = [
            schema for schema in tools_schemas
            if schema["function"]["name"] not in self.EXCLUDED_TOOLS
        ]
        self.model = model
        self.client = client
        self.always_content = self.skill_loader.get_always_skills_content()

    @property
    def name(self) -> str:
        return "use_subagent"

    @property
    def description(self) -> str:
        return f"""调用子Agent来完成一项任务。
比如：分析代码结构；需要多次联网搜索或资料收集的任务(如研究报告、deepsearch、RAG)；需要多次工具调用的任务···
特点:
- 子Agent拥有完全独立的空白上下文，不共享主Agent上文历史，子Agent内部历史不保存
- 子Agent可使用除{self.EXCLUDED_TOOLS}外的所有tools和skills
- 子Agent执行完成后返回完整结果
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "提供一个清晰、完整、独立的任务描述(经过指代消解/省略恢复)，包括:任务目标、预期输出格式、任何约束条件或特殊要求、必要的背景信息(完整路径、文件名等)。",
                }
            },
            "required": ["task"]
        }

    async def execute(
        self,
        task: str,
        **kwargs
    ) -> str:
        """
        执行use_subagent工具
        task: 完整独立的任务描述
        **kwargs: 包含channel_id, input_q, output_q, channel_workspace等
        返回: 子Agent执行结果
        """
        channel_id = kwargs.get("channel_id", "unknown")
        input_q = kwargs.get("input_q")
        output_q = kwargs.get("output_q")
        channel_workspace = kwargs.get("channel_workspace")

        if not input_q or not output_q:
            return "错误: use_subagent工具需要input_q和output_q参数"

        if not channel_workspace:
            return "错误: use_subagent工具需要channel_workspace参数"

        # 创建子Agent
        sub_agent = SubAgent(
            config=self.config,
            tools_schemas=self.tools_schemas,
            skill_loader=self.skill_loader,
            always_content=self.always_content,
            model=self.model,
            client=self.client,
            max_iterations=15,
        )

        # 运行子Agent
        try:
            result = await sub_agent.run(
                task_description=task,
                channel_id=channel_id,            # 与主Agent相同的channel_id
                input_q=input_q,                  # 共享输入队列
                output_q=output_q,                # 共享输出队列
                channel_workspace=channel_workspace,  # 共享channel_workspace
            )
            return f"【子Agent执行结果】\n{result}"
        except Exception as e:
            return f"【子Agent执行失败】错误: {str(e)}"
