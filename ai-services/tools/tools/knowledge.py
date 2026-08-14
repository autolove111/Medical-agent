"""
工具：从医学知识库检索相关内容（触发 RAG）
"""

from __future__ import annotations
import logging

from tools.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class SearchKnowledgeTool(BaseTool):
    """从医学知识库检索专业医学知识"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge",
            description="从医学知识库检索专业医学知识。返回相关文献片段及来源。",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="基于用户问题生成一段假设性回答，用于向量检索。如用户问'肌酐偏高怎么办'，生成'肌酐偏高可能由肾功能不全、脱水、高蛋白饮食等引起，诊断标准为血肌酐超过参考范围，需结合GFR分期评估肾功能，治疗包括控制原发病、饮食调整等'。回答不需要完全正确，只需在语义上接近真实医学文献。",
                    required=True,
                ),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "")
        if not query:
            return ToolResult(content="错误：请提供检索关键词", success=False)

        try:
            from rag.retrieval.query_engine import get_query_engine

            engine = get_query_engine()
            answer, nodes = engine.retrieve(query)

            if not nodes:
                return ToolResult(
                    content=f"未找到与'{query}'相关的医学知识。",
                    success=False,
                )

            # 构建结构化结果
            results = []
            for i, node in enumerate(nodes, 1):
                metadata = node.metadata or {}
                results.append({
                    "index": i,
                    "content": node.get_content(),
                    "source": metadata.get("file_name", "unknown"),
                    "heading": metadata.get("heading", ""),
                    "score": round(node.score, 3) if node.score else None,
                })

            return ToolResult(
                content=answer,
                metadata={"results": results, "query": query},
            )

        except Exception as e:
            logger.error("Knowledge search failed: %s", e)
            return ToolResult(content=f"知识检索失败：{e}", success=False)
