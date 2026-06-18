"""
工具：分析单个检验指标是否异常，返回详细判定结果
"""

from __future__ import annotations
import logging

from harness.tool.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class AnalyzeIndicatorTool(BaseTool):
    """分析单个检验指标是否异常"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_indicator",
            description="分析单个检验指标是否异常，返回详细判定结果",
            parameters=[
                ToolParameter(
                    name="indicator",
                    type="string",
                    description="指标英文名，如 creatinine、uric_acid",
                    required=True,
                ),
                ToolParameter(
                    name="value",
                    type="number",
                    description="检测值",
                    required=True,
                ),
                ToolParameter(
                    name="age",
                    type="integer",
                    description="患者年龄",
                    required=True,
                ),
                ToolParameter(
                    name="gender",
                    type="string",
                    description="患者性别",
                    enum=["男", "女"],
                    required=True,
                ),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        indicator = kwargs.get("indicator", "")
        value = float(kwargs.get("value", 0))
        age = int(kwargs.get("age", 0))
        gender = kwargs.get("gender", "")

        try:
            from app.business.indicator_classifier import classify_indicator
            result = classify_indicator(indicator, value, age=age, gender=gender)

            content = (
                f"指标名称：{result['name']}\n"
                f"检测值：{result['value']} {result['unit']}\n"
                f"参考范围：{result['ref_range']}\n"
                f"状态：{result['status']}\n"
                f"{'⚠️ 危急值！' if result['is_critical'] else ''}\n"
                f"临床意义：{result['description']}\n"
                f"年龄分组：{result['age_group']}"
            )
            return ToolResult(content=content)
        except Exception as e:
            logger.error("Indicator analysis failed: %s", e)
            return ToolResult(content=f"指标分析失败：{e}", success=False)
