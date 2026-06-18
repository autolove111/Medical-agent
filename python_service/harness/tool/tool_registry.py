"""
工具注册表

管理所有已注册的工具实例，提供按名称查找和批量导出 schema 的能力。
"""

from __future__ import annotations
from typing import Dict, List

from harness.tool.tool_protocol import BaseTool


class ToolRegistry:
    """工具注册表：注册、查找、导出 schema"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具（以 tool.get_definition().name 为 key）"""
        definition = tool.get_definition()
        self._tools[definition.name] = tool

    def get(self, name: str) -> BaseTool:
        """按名称获取工具"""
        return self._tools[name]

    def get_all(self) -> List[BaseTool]:
        """获取所有已注册工具"""
        return list(self._tools.values())

    def get_all_openai_schemas(self) -> List[Dict]:
        """导出所有工具的 OpenAI function calling schema"""
        return [tool.get_definition().to_openai_schema() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
