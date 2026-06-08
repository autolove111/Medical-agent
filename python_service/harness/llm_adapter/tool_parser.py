"""
工具调用解析器：从模型输出中提取工具调用意图

支持两种格式：
1. XML 格式（推荐，解析更可靠）：
   <tool_call>
   {"name": "search_knowledge", "args": {"query": "CKD分期标准"}}
   </tool_call>

2. 旧格式（兼容）：
   Action: tool_name
   Action Input: {"key": "value"}

容错设计：JSON 解析失败时回退到正则提取关键字段
"""

from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """解析出的工具调用"""
    name: str
    args: dict = field(default_factory=dict)
    raw_text: str = ""
    is_valid: bool = True
    error: str = ""


def parse_tool_call(text: str) -> Optional[ToolCall]:
    """
    从模型输出中提取工具调用

    返回 ToolCall 或 None（表示这是最终回复，无需工具调用）
    """
    if not text:
        return None

    # 格式 1: XML 格式 <tool_call>...</tool_call>
    xml_match = re.search(
        r'<tool_call>\s*(.+?)\s*</tool_call>',
        text, re.DOTALL | re.IGNORECASE,
    )
    if xml_match:
        inner = xml_match.group(1).strip()
        try:
            data = json.loads(inner)
            return ToolCall(
                name=data.get("name", ""),
                args=data.get("args", data.get("parameters", {})),
                raw_text=text,
            )
        except json.JSONDecodeError:
            # JSON 容错：尝试修复常见错误
            repaired = _repair_json(inner)
            if repaired:
                try:
                    data = json.loads(repaired)
                    return ToolCall(
                        name=data.get("name", ""),
                        args=data.get("args", data.get("parameters", {})),
                        raw_text=text,
                    )
                except json.JSONDecodeError:
                    pass

    # 格式 2: Action / Action Input 格式
    action_match = re.search(
        r'Action:\s*(\S+)',
        text, re.IGNORECASE,
    )
    if action_match:
        name = action_match.group(1).strip()
        args = {}

        input_match = re.search(
            r'Action Input:\s*(.+?)(?:\n|$)',
            text, re.IGNORECASE | re.DOTALL,
        )
        if input_match:
            raw_args = input_match.group(1).strip()
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                repaired = _repair_json(raw_args)
                if repaired:
                    try:
                        args = json.loads(repaired)
                    except json.JSONDecodeError:
                        args = {"raw": raw_args}

        return ToolCall(name=name, args=args, raw_text=text)

    # 格式 3: 代码块中的 JSON（{...}）
    json_match = re.search(
        r'```(?:json)?\s*(\{.*?\})\s*```',
        text, re.DOTALL,
    )
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if "name" in data and ("args" in data or "parameters" in data):
                return ToolCall(
                    name=data.get("name", ""),
                    args=data.get("args", data.get("parameters", {})),
                    raw_text=text,
                )
        except json.JSONDecodeError:
            pass

    # 没有工具调用 → 最终回复
    return None


def is_tool_call(text: str) -> bool:
    """快速判断模型输出是否包含工具调用"""
    return parse_tool_call(text) is not None


def extract_final_response(text: str) -> str:
    """从含工具调用的输出中提取最终回复部分"""
    # 移除 tool_call 标签内容
    cleaned = re.sub(
        r'<tool_call>.*?</tool_call>',
        '', text, flags=re.DOTALL | re.IGNORECASE,
    )
    # 移除 Action/Action Input 块
    cleaned = re.sub(
        r'Action:.*?(?:\nAction Input:.*?)?(?:\n|$)',
        '', cleaned, flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(
        r'```json\s*\{.*?\}\s*```',
        '', cleaned, flags=re.DOTALL,
    )
    return cleaned.strip()


def _repair_json(text: str) -> Optional[str]:
    """容错修复常见 JSON 错误"""
    t = text.strip()
    # 修复单引号
    t = t.replace("'", '"')
    # 修复中文引号
    t = t.replace('“', '"').replace('”', '"')
    t = t.replace('‘', "'").replace('’', "'")
    # 修复尾部逗号
    t = re.sub(r',\s*}', '}', t)
    t = re.sub(r',\s*]', ']', t)
    # 确保是 JSON 对象
    if not t.startswith('{'):
        t = '{' + t
    if not t.endswith('}'):
        t = t + '}'
    return t
