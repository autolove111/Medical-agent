"""
prompts —— Prompt 模块

只暴露一个函数：load_prompt(template_id, **variables)

使用方式：
    from prompts import load_prompt

    messages = load_prompt(
        "report_analysis",
        user_profile={"age": 30, "gender": "男"},
        knowledge="...",
        report_data="...",
    )
"""

from prompts.loader import load_prompt

__all__ = ["load_prompt"]
