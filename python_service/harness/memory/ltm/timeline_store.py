"""
timeline_store.py
~~~~~~~~~~~~~~~~~
时间轴事件存储：PostgreSQL 实现。
"""

import logging
from typing import List, Optional

from ..models.timeline_event import TimelineEvent

logger = logging.getLogger(__name__)


class TimelineStore:
    """时间轴事件存储（PostgreSQL）"""

    def __init__(self, db=None):
        from app.persistence.repositories.session_data_repo import SessionDataRepo
        self._repo = SessionDataRepo(db=db)

    def add(self, event: TimelineEvent) -> None:
        self._repo.add_event(
            patient_id=event.user_id,
            session_id=event.session_id,
            event_type=event.event_type,
            content=event.content,
            raw_data=event.structured_data or {},
        )
        logger.debug("Added event: %s (%s)", event.event_id, event.event_type)

    def query(
        self,
        user_id: str,
        event_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[TimelineEvent]:
        rows = self._repo.get_events(
            patient_id=user_id,
            event_type=event_type or "",
            limit=limit,
        )
        return [
            TimelineEvent(
                event_id=str(r["id"]),
                user_id=user_id,
                session_id=r["session_id"],
                event_type=r["event_type"],
                content=r["content"],
                structured_data=r.get("raw_data", {}),
            )
            for r in rows
        ]
