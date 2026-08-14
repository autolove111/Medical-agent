"""
记忆快照 Repository — 存取 messages / summary / message_len
"""

from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from memory.persistence.models import MemorySnapshot
from memory.persistence.database import get_session

logger = logging.getLogger(__name__)


class MemorySnapshotRepo:

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._own = db is None

    def _get_db(self) -> Session:
        return self._db if self._db is not None else get_session()

    def _close(self, db: Session):
        if self._own:
            db.close()

    def save(self, patient_id: str, session_id: str,
             messages: list[dict], summary: list[dict], message_len: int) -> None:
        """存入快照（同一 session 只保留一条，更新而非插入）"""
        db = self._get_db()
        try:
            row = db.query(MemorySnapshot).filter(
                MemorySnapshot.patient_id == patient_id,
                MemorySnapshot.session_id == session_id,
            ).first()
            if row:
                row.message_len = message_len
                row.set_messages(messages)
                row.set_summary(summary)
            else:
                row = MemorySnapshot(
                    patient_id=patient_id,
                    session_id=session_id,
                    message_len=message_len,
                )
                row.set_messages(messages)
                row.set_summary(summary)
                db.add(row)
            db.commit()

            # 清理同 session 的历史冗余行（保留当前这条）
            db.query(MemorySnapshot).filter(
                MemorySnapshot.patient_id == patient_id,
                MemorySnapshot.session_id == session_id,
                MemorySnapshot.id != row.id,
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            self._close(db)

    def load(self, patient_id: str, session_id: str) -> Optional[dict]:
        """读取最新一条快照，返回 {messages, summary, message_len} 或 None"""
        db = self._get_db()
        try:
            row = db.query(MemorySnapshot).filter(
                MemorySnapshot.patient_id == patient_id,
                MemorySnapshot.session_id == session_id,
            ).order_by(desc(MemorySnapshot.id)).first()
            if not row:
                return None
            return {
                "messages": row.get_messages(),
                "summary": row.get_summary(),
                "message_len": row.message_len,
            }
        finally:
            self._close(db)
