#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   tavily_search.py
@Author  :   zemin
@Desc    :   Tavily 搜索工具
'''

from cheerclaw.tools_module.base import Tool


class TavilySearchTool(Tool):

    def __init__(self):
        self._client = None

    @property
    def name(self) -> str:
        return "tavily_search"

    @property
    def description(self) -> str:
        return """使用 Tavily AI 搜索引擎进行网络搜索。返回结构化的搜索结果。"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询内容"
                }
            },
            "required": ["query"]
        }

    @property
    def required_packages(self) -> list[str]:
        return ["tavily-python"]

    def _get_client(self):
        if self._client is None:
            try:
                from tavily import TavilyClient
            except ImportError:
                raise ImportError(
                    "未安装 tavily-python 包，请运行: pip3 install tavily-python"
                )

            from cheerclaw.config.config_loader import load_config
            config = load_config()
            api_key = config.tavily.api_key if config and config.tavily else ""

            if not api_key:
                raise ValueError(
                    "Tavily 还没有配置 API Key，请在 config.json 中添加 tavily.api_key 配置"
                )

            self._client = TavilyClient(api_key)

        return self._client

    async def execute(
        self,
        query: str,
        **kwargs
    ) -> str:
        try:
            client = self._get_client()

            if not query or not query.strip():
                return "错误: 搜索查询内容不能为空"

            search_depth = "advanced"  # 深度搜索
            max_results = 5  # 返回5条结果

            response = client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results
            )

            return self._format_results(response)

        except ImportError as e:
            return f"错误: {str(e)}"
        except ValueError as e:
            return f"错误: {str(e)}"
        except Exception as e:
            return f"搜索失败: {str(e)}"

    def _format_results(self, response: dict) -> str:
        if not response:
            return "搜索未返回结果"

        results = response.get("results", [])
        if not results:
            return "未找到相关结果"

        lines = [f"🔍 Tavily 搜索结果 (共 {len(results)} 条)"]

        for i, result in enumerate(results, 1):
            title = result.get("title", "无标题")
            url = result.get("url", "")
            content = result.get("content", "")
            score = result.get("score", 0)

            lines.append(f"\n【{i}】{title}")
            if url:
                lines.append(f"🔗 链接: {url}")
            # if score:
            #     lines.append(f"⭐ 相关度: {score:.2f}")
            if content:
                # 限制内容长度，避免过长
                content_preview = content[:5000] + "..." if len(content) > 5000 else content
                lines.append(f"📝 内容: {content_preview}")

        # 添加搜索建议
        answer = response.get("answer")
        if answer:
            lines.append(f"\n💡 智能回答:\n{answer}")

        return "\n".join(lines)
    