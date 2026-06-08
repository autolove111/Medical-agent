"""
summary_store.py
~~~~~~~~~~~~~~~~
会话总结存储：PostgreSQL 实现。
"""

import logging
from typing import List

from ..models.session_summary import SessionSummary

logger = logging.getLogger(__name__)


class SummaryStore:
    """会话总结存储（PostgreSQL）"""

    def __init__(self, db=None):
        from app.persistence.repositories.session_data_repo import SessionDataRepo
        self._repo = SessionDataRepo(db=db)

    def save(self, summary: SessionSummary) -> None:
        self._repo.add_summary(
            patient_id=summary.user_id,
            session_id=summary.session_id,
            summary_text=summary.summary_text,
            raw_data={
                "model_used": summary.model_used,
                "chief_complaint": summary.chief_complaint or "",
                "key_symptoms": summary.key_symptoms or [],
                "suggestions": summary.suggestions or [],
                "follow_ups": summary.follow_ups or [],
            },
        )
        logger.debug("Saved summary: %s", summary.session_id)

    def get_by_user(self, user_id: str, limit: int = 5) -> List[SessionSummary]:
        rows = self._repo.get_summaries(patient_id=user_id, limit=limit)
        return [
            SessionSummary(
                summary_id="",
                user_id=user_id,
                session_id=r["session_id"],
                summary_text=r["summary_text"],
            )
            for r in rows
        ]
