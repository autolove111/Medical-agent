"""
context_window_control
~~~~~~~~~~~~~~~~~~~~~~
上下文窗口控制器 — 根据总 token 数，分配各类内容的预算。

7 类内容：
  1. def_prompt   — 系统基底（角色定义）
  2. profile       — 患者画像
  3. format        — 格式/CoT 指令
  4. summary       — 会话总结
  5. temp          — 临时消息预留（工具调用等）
  6. history       — 对话消息（短期记忆）
  7. output        — 本轮输出预留
"""

from __future__ import annotations
from dataclasses import dataclass


# ============================================================
# Token 估算
# ============================================================

def estimate_tokens(text: str) -> int:
    """CJK 字符 1.5 token，其他 0.25 token"""
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return int(cjk * 1.5 + (len(text) - cjk) * 0.25)


def tokens_to_chars(max_tokens: int) -> int:
    """token 上限转为字符上限（按 CJK 为主估算）"""
    return int(max_tokens / 1.5)


# ============================================================
# 默认分配比例
# ============================================================

DEFAULT_ALLOCATION = {
    "def_prompt":  0.08,   #  8% — 系统基底
    "profile":     0.05,   #  5% — 患者画像
    "format":      0.05,   #  5% — 格式/CoT 指令
    "summary":     0.10,   # 10% — 会话总结
    "temp":        0.07,   #  7% — 临时消息预留
    "history":     0.45,   # 45% — 对话消息
    "output":      0.20,   # 20% — 本轮输出预留
}


# ============================================================
# 各类内容的限制
# ============================================================

@dataclass
class ContentLimit:
    """单类内容的 token/字符限制"""
    name: str
    tokens: int
    chars: int


# ============================================================
# ContextWindowControl
# ============================================================

class ContextWindowControl:
    """
    上下文窗口控制器。

    使用方式：
        ctrl = ContextWindowControl(total_tokens=32768)
        limit = ctrl.get_limit("history")
        print(limit.tokens)  # 14745
        print(limit.chars)   # 9830
    """

    def __init__(self, total_tokens: int = 100000, output_ratio: float = 0.20,
                 allocation: dict[str, float] = None):
        """
        Args:
            total_tokens: 模型的总上下文窗口 token 数
            output_ratio: 输出预留比例（默认 20%）
            allocation: 自定义各类分配比例（可选）
        """
        self.total_tokens = total_tokens
        self.output_ratio = output_ratio
        self.available = int(total_tokens * (1 - output_ratio))
        self.allocation = allocation or DEFAULT_ALLOCATION

        # 预计算各类限制
        self._limits: dict[str, ContentLimit] = {}
        for name, ratio in self.allocation.items():
            max_tokens = int(self.available * ratio)
            self._limits[name] = ContentLimit(
                name=name,
                tokens=max_tokens,
                chars=tokens_to_chars(max_tokens),
            )

    def get_limit(self, content_type: str) -> ContentLimit:
        """获取单类内容的限制"""
        return self._limits.get(content_type, ContentLimit(name=content_type, tokens=0, chars=0))

    def get_all_limits(self) -> dict[str, ContentLimit]:
        """获取所有类别的限制"""
        return self._limits

    def check(self, content_type: str, text: str) -> bool:
        """检查文本是否超出限制，True=超限"""
        limit = self.get_limit(content_type)
        return estimate_tokens(text) > limit.tokens

    def truncate(self, content_type: str, text: str) -> str:
        """截断文本到限制内"""
        limit = self.get_limit(content_type)
        if estimate_tokens(text) <= limit.tokens:
            return text
        return text[:limit.chars] + "..."

    def print_summary(self) -> None:
        """打印分配摘要"""
        total_used = sum(l.tokens for l in self._limits.values())
        print(f"\n{'='*50}")
        print(f"📐 总窗口:   {self.total_tokens} tokens")
        print(f"📤 输出预留: {int(self.total_tokens * self.output_ratio)} tokens")
        print(f"📥 可用:     {self.available} tokens")
        print(f"{'='*50}")
        for name, l in self._limits.items():
            pct = l.tokens / self.available * 100
            print(f"  {name:12s}: {l.tokens:6d} tokens ({pct:4.1f}%) = {l.chars:5d} chars")
        print(f"  {'合计':12s}: {total_used:6d} tokens")
        print(f"{'='*50}")
