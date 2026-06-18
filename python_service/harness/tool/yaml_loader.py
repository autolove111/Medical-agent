"""
工具描述加载器 — 读取 tools.yaml，生成工具描述文本

供 prompt 第3层（工具描述）使用。
"""

from __future__ import annotations
import yaml
from pathlib import Path

_TOOLS_FILE = Path(__file__).parent / "tools.yaml"


def load_tools_text() -> str:
    """加载 tools.yaml 并格式化为 prompt 可用的文本"""
    with open(_TOOLS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    lines = ["【可用工具】"]
    for tool in data.get("tools", []):
        lines.append(f"- {tool['name']}: {tool['description']}")
        params = tool.get("parameters", {})
        for pname, pinfo in params.items():
            lines.append(f"  参数 {pname} ({pinfo['type']}): {pinfo['description']}")
    return "\n".join(lines)
