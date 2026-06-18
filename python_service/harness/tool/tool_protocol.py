"""
工具协议层定义

定义工具的参数、定义、结果、基类。
所有具体工具必须继承 BaseTool 并实现 get_definition() 和 execute()。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict
from abc import ABC, abstractmethod


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str           # "string", "integer", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None
    items: Optional[Dict[str, Any]] = None   # for array type

    def to_schema(self) -> Dict[str, Any]:
        """转换为 JSON Schema 属性"""
        schema = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum is not None:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        if self.type == "array" and self.items:
            schema["items"] = self.items
        return schema


@dataclass
class ToolDefinition:
    """工具完整定义：名称 + 描述 + 参数列表"""
    name: str
    description: str
    parameters: List[ToolParameter]

    def to_openai_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling 格式"""
        properties = {}
        required = []
        for p in self.parameters:
            properties[p.name] = p.to_schema()
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


@dataclass
class ToolResult:
    """工具执行结果"""
    content: str
    success: bool = True
    metadata: Optional[Dict[str, Any]] = None


class BaseTool(ABC):
    """工具基类，所有具体工具必须继承"""

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """返回工具定义（名称、描述、参数）"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具，返回结果"""
        pass
