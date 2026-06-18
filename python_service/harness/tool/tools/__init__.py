"""
医疗工具集 — 汇总注册所有工具

每个工具文件导出一个 BaseTool 子类，此处实例化并注册到 ToolRegistry。
"""

from harness.tool.tool_registry import ToolRegistry
from harness.tool.tools.reference import ReferenceLookupTool
from harness.tool.tools.egfr import CalculateEgfrTool
from harness.tool.tools.knowledge import SearchKnowledgeTool
from harness.tool.tools.indicator import AnalyzeIndicatorTool


def get_registry() -> ToolRegistry:
    """获取包含所有默认工具的注册表"""
    registry = ToolRegistry()
    registry.register(ReferenceLookupTool())
    registry.register(CalculateEgfrTool())
    registry.register(SearchKnowledgeTool())
    registry.register(AnalyzeIndicatorTool())
    return registry


__all__ = ["get_registry"]