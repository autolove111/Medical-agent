"""
state_tracker_engine.py
~~~~~~~~~~~~~~~~~~~~~~~
状态跟踪器引擎：调用LLM更新状态。
"""

import json
import logging
from typing import Callable, Dict, List, Optional

from ..models.state_tracker import StateTracker

logger = logging.getLogger(__name__)

STATE_UPDATE_PROMPT = """你是一个医疗问诊助手的状态分析器。根据对话内容，输出状态更新的JSON。

当前状态：
{current_state}

最新对话：
{recent_conversation}

请输出JSON格式的状态更新：
{{
    "current_phase": "问诊阶段（greeting/history_taking/symptom_inquiry/examination_suggestion/conclusion）",
    "collected": {{"新收集的键": "值"}},
    "pending": ["待确认的信息1", "待确认的信息2"],
    "conclusions": ["当前结论"]
}}

只输出JSON，不要有其他内容："""


class StateTrackerEngine:
    """状态跟踪器引擎"""

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None):
        self.llm_caller = llm_caller

    def update(
        self, tracker: StateTracker, recent_messages: List[Dict]
    ) -> StateTracker:
        """根据最新对话更新状态跟踪器"""
        if not self.llm_caller:
            return tracker

        current_state = tracker.to_prompt_text()
        conversation_text = self._format_messages(recent_messages)

        prompt = STATE_UPDATE_PROMPT.format(
            current_state=current_state,
            recent_conversation=conversation_text,
        )

        try:
            response = self.llm_caller(prompt)
            update_data = self._parse_json(response)
            if update_data:
                tracker.apply_update(update_data)
                logger.debug("State updated: phase=%s", tracker.current_phase)
        except Exception as e:
            logger.error("Failed to update state: %s", e)

        return tracker

    def _format_messages(self, messages: List[Dict]) -> str:
        parts = []
        for msg in messages[-6:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def _parse_json(self, text: str) -> Optional[Dict]:
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON: %s", e)
            return None
