"""
prompts.loader
~~~~~~~~~~~~~~
Prompt 加载器 —— 只暴露一个函数 load_prompt()

使用方式：
    from prompts import load_prompt

    messages = load_prompt("report_analysis", user_profile={...}, report_data="...")
    # 返回: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
"""

from __future__ import annotations

import yaml
from pathlib import Path
from jinja2 import Template
from typing import Any

# 模板目录
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_prompt(template_id: str, **variables: Any) -> list[dict]:
    """
    加载 Prompt 模板并注入变量，返回 messages 列表。

    Args:
        template_id: 模板 ID（不含 .yaml 后缀）
        **variables: 模板变量

    Returns:
        [
            {"role": "system", "content": "..."},
        ]
    """
    # 1. 加载 YAML 模板
    template_path = _TEMPLATES_DIR / f"{template_id}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt 模板不存在: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = yaml.safe_load(f)

    # 2. 按五层架构拼接 system message
    system_parts = []

    if "role" in template:
        system_parts.append(template["role"].strip())

    if "task" in template:
        system_parts.append("## 任务\n" + template["task"].strip())

    if "rules" in template:
        system_parts.append("## 规则\n" + template["rules"].strip())

    if "format" in template and template["format"]:
        system_parts.append("## 输出格式\n" + template["format"].strip())

    # 兼容旧格式（直接有 system 字段）
    if "system" in template:
        system_parts.append(template["system"].strip())

    # 3. 渲染变量（先渲染 context）
    if "context" in template:
        context_content = Template(template["context"]).render(**variables)
        system_parts.append(context_content.strip())

    # 4. 渲染所有变量
    if system_parts:
        system_content = "\n\n".join(system_parts)
        system_content = Template(system_content).render(**variables)
        return [{"role": "system", "content": system_content}]

    return []


def list_templates() -> list[str]:
    """列出所有可用的模板 ID"""
    return [p.stem for p in _TEMPLATES_DIR.glob("*.yaml")]
