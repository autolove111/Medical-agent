"""
工具：查询检验指标的参考范围和临床意义
"""

from __future__ import annotations
import json
import logging

from harness.tool.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class ReferenceLookupTool(BaseTool):
    """查询检验指标的参考范围和临床意义"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="reference_lookup",
            description="查询检验指标的参考范围、临床意义",
            parameters=[
                ToolParameter(
                    name="indicator",
                    type="string",
                    description="指标英文名，如 creatinine、uric_acid",
                    required=True,
                ),
                ToolParameter(
                    name="age",
                    type="integer",
                    description="患者年龄",
                    required=False,
                    default=0,
                ),
                ToolParameter(
                    name="gender",
                    type="string",
                    description="患者性别",
                    enum=["男", "女"],
                    required=False,
                    default="男",
                ),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        indicator = kwargs.get("indicator", "")

        try:
            from harness.memory.knowledge.reference_ranges import REFERENCE_RANGES, format_reference_text
            from app.business.indicator_classifier import _resolve_key

            resolved = _resolve_key(indicator)
            if resolved in REFERENCE_RANGES:
                return ToolResult(content=format_reference_text(resolved))

            return ToolResult(
                content=f"未找到指标 '{indicator}' 的参考范围信息。",
                success=False,
            )
        except Exception as e:
            logger.error("Reference lookup failed: %s", e)
            return ToolResult(content=f"查询参考范围失败：{e}", success=False)
