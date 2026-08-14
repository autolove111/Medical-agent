"""
医疗工具集 — 汇总注册所有工具
"""

from tools.tool_registry import ToolRegistry
from tools.tools.knowledge import SearchKnowledgeTool


def get_registry() -> ToolRegistry:
    """获取包含所有默认工具的注册表"""
    registry = ToolRegistry()
    registry.register(SearchKnowledgeTool())
    return registry


__all__ = ["get_registry"]
