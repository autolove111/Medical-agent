"""
session_lifecycle.py
~~~~~~~~~~~~~~~~~~~~
会话生命周期管理器。
"""

import json
import logging
import time
import uuid
from typing import Callable, Dict, List, Optional

from ..ltm.ltm_manager import LTMManager
from ..stm.stm_manager import STMManager
from ..models.user_profile import UserProfile
from ..models.timeline_event import TimelineEvent, EventType
from ..models.conversation_message import ConversationMessage
from ..models.session_summary import SessionSummary

logger = logging.getLogger(__name__)

EVENT_EXTRACT_PROMPT = """从以下医疗对话中提取事件，输出JSON数组。

对话内容：
{conversation}

事件类型：
- symptom: 症状描述
- lab_result: 化验结果
- imaging: 影像报告

输出格式：
[
    {{"event_type": "symptom", "content": "症状描述", "structured_data": {{}}}},
    {{"event_type": "lab_result", "content": "化验结果描述", "structured_data": {{"test_name": "...", "items": [...]}}}}
]

只输出JSON数组，没有事件则输出空数组 []："""

SUMMARY_PROMPT = """请根据以下医疗对话生成会话总结，严格控制在200字以内。

对话内容：
{conversation}

请包含以下内容：
- 主诉
- 关键症状变化
- 医生建议
- 已执行检查
- 待跟进事项

总结："""


class SessionLifecycle:
    """会话生命周期管理器"""

    def __init__(
        self,
        ltm_manager: LTMManager = None,
        llm_caller: Optional[Callable[[str], str]] = None,
        redis_client=None,
        db=None,
    ):
        self.ltm = ltm_manager or LTMManager(db=db)
        self.llm_caller = llm_caller
        self._redis = redis_client

    def start_session(self, user_id: str) -> STMManager:
        """开始新会话"""
        session_id = f"session_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        user_profile = self.ltm.get_user_profile(user_id)

        stm = STMManager(
            session_id=session_id,
            user_id=user_id,
            redis_client=self._redis,
            llm_caller=self.llm_caller,
            ltm_manager=self.ltm,
        )
        stm.user_profile = user_profile

        logger.info("Session started: %s (user=%s)", session_id, user_id)
        return stm

    def end_session(self, stm: STMManager) -> None:
        """结束会话"""
        session_id = stm.session_id
        user_id = stm.user_id

        logger.info("Ending session: %s", session_id)

        all_messages = stm.get_all_messages()

        # 1. 生成会话总结
        summary = self._generate_summary(session_id, user_id, all_messages)
        if summary:
            self.ltm.save_summary(summary)

        # 2. 提取事件
        events = self._extract_events(session_id, user_id, all_messages)
        for event in events:
            self.ltm.add_event(event)

        # 3. 更新用户画像
        self._update_user_profile(user_id, all_messages)

        # 4. 保存对话原文
        conversation_messages = self._to_conversation_messages(
            session_id, user_id, all_messages
        )
        self.ltm.save_conversation(session_id, conversation_messages)

        # 5. 清理STM
        stm.clear()

        logger.info(
            "Session ended: %s (summary=%s, events=%d, messages=%d)",
            session_id,
            "generated" if summary else "skipped",
            len(events),
            len(conversation_messages),
        )

    def recover_session(
        self, session_id: str, user_id: str
    ) -> Optional[STMManager]:
        """恢复中断的会话"""
        stm = STMManager(
            session_id=session_id,
            user_id=user_id,
            redis_client=self._redis,
            llm_caller=self.llm_caller,
            ltm_manager=self.ltm,
        )

        if stm.load_from_redis():
            stm.user_profile = self.ltm.get_user_profile(user_id)
            logger.info("Session recovered: %s", session_id)
            return stm

        logger.warning("Failed to recover session: %s", session_id)
        return None

    # ---- 内部方法 ----

    def _generate_summary(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict],
    ) -> Optional[SessionSummary]:
        if not self.llm_caller or not messages:
            return None

        conversation = self._format_conversation(messages)
        prompt = SUMMARY_PROMPT.format(conversation=conversation)

        try:
            summary_text = self.llm_caller(prompt)
            if len(summary_text) > 400:
                summary_text = summary_text[:400] + "..."

            return SessionSummary(
                user_id=user_id,
                session_id=session_id,
                summary_text=summary_text,
                model_used="llm",
            )
        except Exception as e:
            logger.error("Failed to generate summary: %s", e)
            return None

    def _extract_events(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict],
    ) -> List[TimelineEvent]:
        if not self.llm_caller or not messages:
            return []

        conversation = self._format_conversation(messages)
        prompt = EVENT_EXTRACT_PROMPT.format(conversation=conversation)

        try:
            response = self.llm_caller(prompt)
            events_data = json.loads(response)

            events = []
            for item in events_data:
                event = TimelineEvent(
                    user_id=user_id,
                    session_id=session_id,
                    event_type=item.get("event_type", EventType.SYMPTOM),
                    content=item.get("content", ""),
                    structured_data=item.get("structured_data", {}),
                )
                events.append(event)
            return events
        except Exception as e:
            logger.error("Failed to extract events: %s", e)
            return []

    def _update_user_profile(
        self, user_id: str, messages: List[Dict]
    ) -> None:
        """从对话中提取用户信息并更新画像"""
        if not messages:
            return

        # 从对话中提取可能的用户信息（基础规则提取）
        profile = self.ltm.get_user_profile(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)

        updated = False
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")

            # 简单规则：检测年龄提及
            import re
            age_match = re.search(r"我(\d{1,3})岁", content)
            if age_match:
                age = int(age_match.group(1))
                if 0 < age < 150:
                    profile.age = age
                    updated = True

            # 检测性别提及
            if "我是男" in content or "男性" in content:
                profile.gender = "男"
                updated = True
            elif "我是女" in content or "女性" in content:
                profile.gender = "女"
                updated = True

        if updated:
            self.ltm.save_user_profile(profile)
            logger.info("Updated user profile from conversation: %s", user_id)

    def _to_conversation_messages(
        self,
        session_id: str,
        user_id: str,
        messages: List[Dict],
    ) -> List[ConversationMessage]:
        result = []
        turn_number = 0
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            if role in ("user", "assistant"):
                turn_number = i // 2 + 1
                result.append(
                    ConversationMessage(
                        user_id=user_id,
                        session_id=session_id,
                        turn_number=turn_number,
                        role=role,
                        content=msg.get("content", ""),
                    )
                )
        return result

    def _format_conversation(self, messages: List[Dict]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                parts.append(f"患者：{content}")
            elif role == "assistant":
                parts.append(f"医生：{content}")
            elif role == "system" and msg.get("type") == "summary":
                parts.append(f"[历史摘要] {content}")
        return "\n".join(parts)
