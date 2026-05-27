"""
对话 Repository：聊天历史持久化
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.persistence.models import ChatMessageModel
from app.persistence.database import get_session

logger = logging.getLogger(__name__)


class ChatRepo:
    """对话记录数据访问层"""

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._own_session = db is None

    def _get_db(self) -> Session:
        if self._db is not None:
            return self._db
        return get_session()

    def _close(self, db: Session):
        if self._own_session:
            db.close()

    def save_message(
        self,
        user_id: str,
        role: str,
        content: str,
        report_id: str = "",
        sources: list[dict] | None = None,
        turn_number: int = 0,
    ) -> ChatMessageModel:
        db = self._get_db()
        try:
            msg = ChatMessageModel(
                user_id=user_id,
                report_id=report_id,
                role=role,
                content=content,
                sources_json=json.dumps(sources or [], ensure_ascii=False),
                turn_number=turn_number,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return msg
        finally:
            self._close(db)

    def get_history(
        self,
        user_id: str,
        report_id: str = "",
        limit: int = 100,
    ) -> list[dict]:
        db = self._get_db()
        try:
            q = (
                db.query(ChatMessageModel)
                .filter(ChatMessageModel.user_id == user_id)
            )
            if report_id:
                q = q.filter(ChatMessageModel.report_id == report_id)
            messages = (
                q.order_by(ChatMessageModel.created_at)
                .limit(limit)
                .all()
            )
            return [
                {
                    "role": m.role,
                    "content": m.content,
                    "sources": m.get_sources(),
                    "turn_number": m.turn_number,
                }
                for m in messages
            ]
        finally:
            self._close(db)

    def get_last_turn(self, user_id: str) -> int:
        """获取最近的对话轮次"""
        db = self._get_db()
        try:
            last = (
                db.query(ChatMessageModel)
                .filter(ChatMessageModel.user_id == user_id)
                .order_by(desc(ChatMessageModel.turn_number))
                .first()
            )
            return last.turn_number if last else 0
        finally:
            self._close(db)
