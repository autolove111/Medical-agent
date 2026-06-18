"""
工具：从医学知识库检索相关内容（触发 RAG）
"""

from __future__ import annotations
import logging

from harness.tool.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class SearchKnowledgeTool(BaseTool):
    """从医学知识库检索专业医学知识"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge",
            description="从医学知识库检索专业医学知识",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="检索问题或关键词",
                    required=True,
                ),
                ToolParameter(
                    name="top_k",
                    type="integer",
                    description="返回结果条数",
                    required=False,
                    default=3,
                ),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "")
        if not query:
            return ToolResult(content="错误：请提供检索关键词", success=False)

        try:
            from service.rag import retrieve_medical_knowledge
            answer, docs = retrieve_medical_knowledge(query)

            if answer:
                return ToolResult(content=answer)
            return ToolResult(
                content=f"未找到与 '{query}' 相关的医学知识。",
                success=False,
            )
        except Exception as e:
            logger.error("Knowledge search failed: %s", e)
            return ToolResult(content=f"知识检索失败：{e}", success=False)
