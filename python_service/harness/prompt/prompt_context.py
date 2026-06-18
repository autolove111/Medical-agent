"""
prompt.prompt_context
~~~~~~~~~~~~~~~~~~~~~
Prompt 组装基类。

维护一个 self.prompt 字典，各 apply_xxx() 方法对对应 key 进行覆盖式修改。
get() 时按顺序拼接所有区域为最终 prompt 字符串。

使用方式：
    builder = BasePromptBuilder(system_prompt="你是一个助手")
    builder.apply_profile({"name": "张三", "age": 30})
    builder.apply_user_input("肌酐偏高怎么办")
    prompt = builder.get()
"""

from __future__ import annotations
from collections import OrderedDict
from harness.context_window.window_control import estimate_tokens, ContextWindowControl


# ============================================================
# Token 工具
# ============================================================
limit = ContextWindowControl()
LAYER_SYSTEM_TOKENS = limit.get_limit("def_prompt").tokens
LAYER_PROFILE_TOKENS = limit.get_limit("profile").tokens
LAYER_FORMAT_TOKENS = limit.get_limit("format").tokens



def count_tokens(text: str) -> int:
    """CJK 字符 1.5 token，其他字符 0.25 token"""
    return estimate_tokens(text)


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """截断文本到指定 token 数"""
    if not text or count_tokens(text) <= max_tokens:
        return text
    chars = int(max_tokens / 1.5)
    return text[:chars] + "..."


# ============================================================
# 基类
# ============================================================

class SystemPromptBuilder:
    """
    Prompt 组装基类。

    内部维护一个 OrderedDict：self.prompt
        key = 区域名称
        value = 该区域的文本内容

    各 apply_xxx() 方法对对应 key 进行覆盖式修改。
    get() 时按插入顺序拼接所有区域为最终 prompt 字符串。

    默认区域顺序：
        system → profile → format → tail

    子类可以：
        - 覆盖任意 apply_xxx() 改变该区域的格式
        - 调用 add_region("name", "content") 新增自定义区域
        - 覆盖 get() 改变拼接逻辑
    """

    def __init__(self):
        # 有序字典：key=区域名, value=文本内容
        self.prompt: list[dict] = []

    # ----------------------------------------------------------
    # 各区域 apply（子类可覆盖）
    # ----------------------------------------------------------

    def apply_def(self, def_prompt: str) -> dict:
        """覆盖系统基底区域"""
        limit_def_prompt = truncate_to_token_limit(def_prompt, LAYER_SYSTEM_TOKENS)
        return {"role": "system", "content": limit_def_prompt}

    def apply_profile(self, profile: dict = None) -> dict:
        """覆盖患者画像区域"""
        if not profile:
            return {"role": "system", "content": ""}
        parts = [
            f"【患者信息】姓名: {profile.get('name', '')} | "
            f"年龄: {profile.get('age', '')} | "
            f"性别: {profile.get('gender', '')}"
        ]
        if profile.get("allergies"):
            parts.append(f"过敏史: {', '.join(profile['allergies'])}")
        if profile.get("chronic_diseases"):
            parts.append(f"慢性病: {', '.join(profile['chronic_diseases'])}")
        if profile.get("medications"):
            parts.append(f"当前用药: {', '.join(profile['medications'])}")
        text = "\n".join(parts)
        limit_text = truncate_to_token_limit(text, LAYER_PROFILE_TOKENS)
        return {"role": "system", "content": limit_text}

    def apply_format(self, format_prompt: str = "") -> dict:
        """覆盖格式/CoT 指令区域"""
        limit_format_prompt = truncate_to_token_limit(format_prompt, LAYER_FORMAT_TOKENS)
        return {"role": "system", "content": limit_format_prompt}

    def add_summary(self, summary: list[dict] ) -> list[dict]:
        """新增会话总结区域（非覆盖）"""
        return summary


    # ----------------------------------------------------------
    # 获取最终 prompt
    # ----------------------------------------------------------

    def get(self, def_prompt: str=None, format_prompt: str=None, profile: dict = None, summary: list[dict] = None) -> list[dict]:
        """
        按顺序返回多个独立的 system message。

        Returns:
            [
                {"role": "system", "content": "基底指令"},
                {"role": "system", "content": "患者画像"},
                {"role": "system", "content": "格式指令"}
            ]
        """
        messages = []
        if def_prompt:  
            messages.append(self.apply_def(def_prompt))
        if profile:
            messages.append(self.apply_profile(profile))
        if format_prompt:
            messages.append(self.apply_format(format_prompt))
        if summary:
            messages.extend(self.add_summary(summary))
        return messages