"""
token_budget.py
~~~~~~~~~~~~~~~
Token预算分配器：按优先级填充上下文窗口。
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """估算token数量"""
    cjk_count = sum(1 for ch in text if "一" <= ch <= "鿿")
    other_count = len(text) - cjk_count
    return int(cjk_count * 1.5 + other_count * 0.25)


class TokenBudget:
    """Token预算分配器"""

    def __init__(
        self,
        context_window: int = 32768,
        output_ratio: float = 0.3,
        buffer_ratio: float = 0.1,
    ):
        self.context_window = context_window
        self.output_tokens = int(context_window * output_ratio)
        self.buffer_tokens = int(context_window * buffer_ratio)
        self.available_tokens = context_window - self.output_tokens - self.buffer_tokens

        logger.info(
            "TokenBudget: total=%d, available=%d, output=%d, buffer=%d",
            context_window,
            self.available_tokens,
            self.output_tokens,
            self.buffer_tokens,
        )

    def allocate(
        self,
        system_prompt: str,
        user_input: str,
        ltm_results: Optional[List[str]] = None,
        stm_messages: Optional[List[Dict]] = None,
        state_text: Optional[str] = None,
    ) -> Dict:
        """
        按优先级分配token预算。

        优先级（从高到低）：
        P1: 系统指令（固定）
        P2: 用户输入（固定）
        P3: LTM检索结果（可裁剪）
        P4: STM近期对话（可裁剪）
        P5: 状态跟踪器（可裁剪）
        """
        result: Dict = {}
        remaining = self.available_tokens

        # P1: 系统指令
        p1_tokens = _estimate_tokens(system_prompt)
        result["system_prompt"] = system_prompt
        result["system_prompt_tokens"] = p1_tokens
        remaining -= p1_tokens

        # P2: 用户输入
        p2_tokens = _estimate_tokens(user_input)
        result["user_input"] = user_input
        result["user_input_tokens"] = p2_tokens
        remaining -= p2_tokens

        # P3: LTM检索结果
        if ltm_results:
            p3_budget = int(remaining * 0.4)
            fitted = self._fit_texts_to_budget(ltm_results, p3_budget)
            result["ltm_results"] = fitted
            result["ltm_results_tokens"] = sum(_estimate_tokens(t) for t in fitted)
            remaining -= result["ltm_results_tokens"]
        else:
            result["ltm_results"] = []
            result["ltm_results_tokens"] = 0

        # P4: STM近期对话
        if stm_messages:
            p4_budget = int(remaining * 0.7)
            fitted = self._fit_messages_to_budget(stm_messages, p4_budget)
            result["stm_messages"] = fitted
            result["stm_messages_tokens"] = sum(
                _estimate_tokens(m.get("content", "")) for m in fitted
            )
            remaining -= result["stm_messages_tokens"]
        else:
            result["stm_messages"] = []
            result["stm_messages_tokens"] = 0

        # P5: 状态跟踪器
        if state_text:
            p5_tokens = _estimate_tokens(state_text)
            if p5_tokens <= remaining:
                result["state_text"] = state_text
                result["state_text_tokens"] = p5_tokens
            else:
                result["state_text"] = state_text[: int(remaining / 1.5)]
                result["state_text_tokens"] = remaining
        else:
            result["state_text"] = ""
            result["state_text_tokens"] = 0

        total_used = sum(
            [
                result["system_prompt_tokens"],
                result["user_input_tokens"],
                result["ltm_results_tokens"],
                result["stm_messages_tokens"],
                result["state_text_tokens"],
            ]
        )
        result["total_used"] = total_used
        result["remaining"] = self.available_tokens - total_used

        logger.debug(
            "Token allocation: system=%d, input=%d, ltm=%d, stm=%d, state=%d, total=%d/%d",
            result["system_prompt_tokens"],
            result["user_input_tokens"],
            result["ltm_results_tokens"],
            result["stm_messages_tokens"],
            result["state_text_tokens"],
            total_used,
            self.available_tokens,
        )

        return result

    def _fit_texts_to_budget(self, texts: List[str], budget: int) -> List[str]:
        result = []
        used = 0
        for text in texts:
            tokens = _estimate_tokens(text)
            if used + tokens <= budget:
                result.append(text)
                used += tokens
            else:
                remaining = budget - used
                if remaining > 50:
                    truncated = text[: int(remaining / 1.5)]
                    result.append(truncated + "...")
                break
        return result

    def _fit_messages_to_budget(
        self, messages: List[Dict], budget: int
    ) -> List[Dict]:
        result = []
        used = 0
        for msg in reversed(messages):
            content = msg.get("content", "")
            tokens = _estimate_tokens(content)
            if used + tokens <= budget:
                result.insert(0, msg)
                used += tokens
            else:
                break
        return result
