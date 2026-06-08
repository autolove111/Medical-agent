"""
ltm_manager.py
~~~~~~~~~~~~~~
长期记忆统一管理器（PostgreSQL）。
"""

import logging
from typing import Dict, List, Optional

from ..models.user_profile import UserProfile
from ..models.timeline_event import TimelineEvent
from ..models.conversation_message import ConversationMessage
from ..models.session_summary import SessionSummary
from .user_profile_store import UserProfileStore
from .timeline_store import TimelineStore
from .conversation_store import ConversationStore
from .summary_store import SummaryStore

logger = logging.getLogger(__name__)


class LTMManager:
    """长期记忆统一管理器（PostgreSQL，2 张表）"""

    def __init__(self, db=None):
        self.user_profiles = UserProfileStore(db=db)
        self.timelines = TimelineStore(db=db)
        self.conversations = ConversationStore(db=db)
        self.summaries = SummaryStore(db=db)
        logger.info("LTMManager initialized (PostgreSQL)")

    # ---- 用户画像 ----

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        return self.user_profiles.get(user_id)

    def save_user_profile(self, profile: UserProfile) -> None:
        self.user_profiles.save(profile)

    def update_user_profile(self, user_id: str, updates: Dict) -> None:
        profile = self.user_profiles.get(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        self.user_profiles.save(profile)

    # ---- 时间轴事件 ----

    def add_event(self, event: TimelineEvent) -> None:
        self.timelines.add(event)

    def get_events(
        self,
        user_id: str,
        event_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[TimelineEvent]:
        return self.timelines.query(user_id, event_type=event_type, limit=limit)

    # ---- 对话原文 ----

    def save_conversation(
        self, session_id: str, messages: List[ConversationMessage]
    ) -> None:
        self.conversations.save_batch(session_id, messages)

    def get_conversation(self, session_id: str) -> List[ConversationMessage]:
        return self.conversations.get_by_session(session_id)

    def cleanup_old_conversations(self, days: int = 7) -> int:
        return self.conversations.delete_before(days)

    # ---- 会话总结 ----

    def save_summary(self, summary: SessionSummary) -> None:
        self.summaries.save(summary)

    def get_summaries(
        self, user_id: str, limit: int = 5
    ) -> List[SessionSummary]:
        return self.summaries.get_by_user(user_id, limit)
