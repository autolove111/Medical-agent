"""
统一会话数据 Repository：session_data CRUD
"""

from __future__ import annotations
import json
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.persistence.models import SessionData
from app.persistence.database import get_session

logger = logging.getLogger(__name__)


class SessionDataRepo:
    """统一会话数据访问层"""

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._own_session = db is None

    def _get_db(self) -> Session:
        if self._db is not None:
            return self._db
        return get_session()

    def _close_if_own(self, db: Session):
        if self._own_session:
            db.close()

    # ---- 写入 ----

    def add_message(
        self,
        patient_id: str,
        session_id: str,
        role: str,
        content: str,
        turn_id: int = 0,
        sources: list = None,
    ) -> SessionData:
        """添加对话消息"""
        db = self._get_db()
        try:
            row = SessionData(
                patient_id=patient_id,
                session_id=session_id,
                event_type="message",
                role=role,
                turn_id=turn_id,
                content=content,
            )
            if sources:
                row.set_raw_data({"sources": sources})
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            self._close_if_own(db)

    def add_event(
        self,
        patient_id: str,
        session_id: str,
        event_type: str,
        content: str,
        raw_data: dict = None,
    ) -> SessionData:
        """添加时间轴事件（lab_result / symptom）"""
        db = self._get_db()
        try:
            row = SessionData(
                patient_id=patient_id,
                session_id=session_id,
                event_type=event_type,
                content=content,
            )
            if raw_data:
                row.set_raw_data(raw_data)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            self._close_if_own(db)

    def add_summary(
        self,
        patient_id: str,
        session_id: str,
        summary_text: str,
        raw_data: dict = None,
    ) -> SessionData:
        """添加会话总结"""
        db = self._get_db()
        try:
            row = SessionData(
                patient_id=patient_id,
                session_id=session_id,
                event_type="summary",
                content=summary_text,
            )
            if raw_data:
                row.set_raw_data(raw_data)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        finally:
            self._close_if_own(db)

    # ---- 查询 ----

    def get_messages(
        self,
        patient_id: str,
        session_id: str,
        limit: int = 500,
    ) -> List[Dict]:
        """获取会话的对话消息（patient_id 为空时按 session_id 查询）"""
        db = self._get_db()
        try:
            q = db.query(SessionData).filter(
                SessionData.session_id == session_id,
                SessionData.event_type == "message",
            )
            if patient_id:
                q = q.filter(SessionData.patient_id == patient_id)
            rows = q.order_by(SessionData.id).limit(limit).all()
            return [
                {
                    "role": r.role,
                    "content": r.content,
                    "turn_id": r.turn_id,
                    "sources": r.get_raw_data().get("sources", []),
                }
                for r in rows
            ]
        finally:
            self._close_if_own(db)

    def get_events(
        self,
        patient_id: str,
        session_id: str = "",
        event_type: str = "",
        limit: int = 50,
    ) -> List[Dict]:
        """获取时间轴事件"""
        db = self._get_db()
        try:
            q = db.query(SessionData).filter(
                SessionData.patient_id == patient_id,
                SessionData.event_type.in_(["lab_result", "symptom"]),
            )
            if session_id:
                q = q.filter(SessionData.session_id == session_id)
            if event_type:
                q = q.filter(SessionData.event_type == event_type)
            rows = q.order_by(desc(SessionData.created_at)).limit(limit).all()

            return [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "event_type": r.event_type,
                    "content": r.content,
                    "raw_data": r.get_raw_data(),
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
        finally:
            self._close_if_own(db)

    def get_summary(
        self,
        patient_id: str,
        session_id: str,
    ) -> Optional[Dict]:
        """获取会话总结"""
        db = self._get_db()
        try:
            row = (
                db.query(SessionData)
                .filter(
                    SessionData.patient_id == patient_id,
                    SessionData.session_id == session_id,
                    SessionData.event_type == "summary",
                )
                .first()
            )
            if not row:
                return None
            return {
                "session_id": row.session_id,
                "summary_text": row.content,
                "raw_data": row.get_raw_data(),
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
        finally:
            self._close_if_own(db)

    def get_summaries(
        self,
        patient_id: str,
        limit: int = 5,
    ) -> List[Dict]:
        """获取患者最近的会话总结"""
        db = self._get_db()
        try:
            rows = (
                db.query(SessionData)
                .filter(
                    SessionData.patient_id == patient_id,
                    SessionData.event_type == "summary",
                )
                .order_by(desc(SessionData.created_at))
                .limit(limit)
                .all()
            )
            return [
                {
                    "session_id": r.session_id,
                    "summary_text": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
        finally:
            self._close_if_own(db)

    def get_all(
        self,
        patient_id: str,
        session_id: str,
    ) -> List[Dict]:
        """获取会话的全部数据（按时间排序）"""
        db = self._get_db()
        try:
            rows = (
                db.query(SessionData)
                .filter(
                    SessionData.patient_id == patient_id,
                    SessionData.session_id == session_id,
                )
                .order_by(SessionData.id)
                .all()
            )
            return [
                {
                    "event_type": r.event_type,
                    "role": r.role,
                    "turn_id": r.turn_id,
                    "content": r.content,
                    "raw_data": r.get_raw_data(),
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
        finally:
            self._close_if_own(db)

    def get_last_turn(self, patient_id: str, session_id: str) -> int:
        """获取最近的对话轮次"""
        db = self._get_db()
        try:
            last = (
                db.query(SessionData)
                .filter(
                    SessionData.patient_id == patient_id,
                    SessionData.session_id == session_id,
                    SessionData.event_type == "message",
                )
                .order_by(desc(SessionData.turn_id))
                .first()
            )
            return last.turn_id if last else 0
        finally:
            self._close_if_own(db)
