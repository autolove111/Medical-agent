"""
conversation_store.py
~~~~~~~~~~~~~~~~~~~~~
对话原文存储：PostgreSQL 实现。
"""

import logging
from typing import List

from ..models.conversation_message import ConversationMessage

logger = logging.getLogger(__name__)


class ConversationStore:
    """对话原文存储（PostgreSQL）"""

    def __init__(self, db=None):
        from app.persistence.repositories.session_data_repo import SessionDataRepo
        self._repo = SessionDataRepo(db=db)

    def save_batch(
        self, session_id: str, messages: List[ConversationMessage]
    ) -> None:
        for msg in messages:
            self._repo.add_message(
                patient_id=msg.user_id,
                session_id=session_id,
                role=msg.role,
                content=msg.content,
                turn_id=msg.turn_number,
            )
        logger.debug("Saved conversation: %s (%d messages)", session_id, len(messages))

    def get_by_session(self, session_id: str) -> List[ConversationMessage]:
        # 需要 patient_id，从消息中推断
        # 这里传空字符串，repo 层需要支持按 session_id 查询
        rows = self._repo.get_messages(patient_id="", session_id=session_id)
        return [
            ConversationMessage(
                user_id="",
                session_id=session_id,
                turn_number=r.get("turn_id", 0),
                role=r.get("role", ""),
                content=r.get("content", ""),
            )
            for r in rows
        ]

    def delete_before(self, days: int = 7) -> int:
        logger.info("Conversation cleanup delegated to DB maintenance")
        return 0
