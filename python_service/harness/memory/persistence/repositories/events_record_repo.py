


"""
对话消息 Repository：session_data WHERE event_type = message
支持医学指标的存储与灵活时间范围查询
"""

from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from harness.memory.persistence.models import EventsData
from harness.memory.persistence.database import get_session

logger = logging.getLogger(__name__)


class EventsRecordRepo:

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._own = db is None

    def _get_db(self) -> Session:
        return self._db if self._db is not None else get_session()

    def _close(self, db: Session):
        if self._own:
            db.close()

    # ========== 写入 ==========

    def save_message(self, patient_id: str, role: str, content: str,
                     scores: dict = None, metrics_involved: Optional[list[str]] = None) -> int:
        """保存一条消息，可选写入评分，返回 turn_id"""
        db = self._get_db()
        try:
            last_turn = db.query(
                func.coalesce(func.max(EventsData.turn_id), 0)
            ).filter(
                EventsData.patient_id == patient_id,
                EventsData.event_type == "message"
            ).scalar()

            next_turn = last_turn + 1

            row = EventsData(
                patient_id=patient_id,
                event_type="message",
                role=role,
                turn_id=next_turn,
                content=content,
            )

            # 写入评分
            if scores:
                row.medical = scores.get("medical", 0.0)
                row.experience = scores.get("experience", 0.0)
                row.profile = scores.get("profile", 0.0)
                row.weight = max([row.medical, row.experience, row.profile])
            else:
                row.weight = 1.0

            if metrics_involved:
                row.set_raw_data({"metrics_involved": metrics_involved})

            db.add(row)
            db.commit()
            return next_turn

        finally:
            self._close(db)

    # ========== 查询 ==========

    def get_metrics_history(self, patient_id: str,
                            start_time: Optional[datetime] = None,
                            end_time: Optional[datetime] = None,
                            limit: int = 5) -> list[dict]:
        """
        查询用户在指定时间段内涉及的历史指标
        """
        db = self._get_db()
        try:
            query = db.query(EventsData).filter(
                EventsData.patient_id == patient_id,
                EventsData.event_type == "message",
                EventsData.role == "assistant"
            )
            
            if start_time:
                query = query.filter(EventsData.created_at >= start_time)
            if end_time:
                query = query.filter(EventsData.created_at <= end_time)
            
            rows = query.order_by(desc(EventsData.created_at)).limit(limit).all()
            
            result = []
            for r in rows:
                metadata = r.get_metadata() or {}
                metrics = metadata.get("metrics_involved", [])
                if metrics:
                    result.append({
                        "metrics": metrics,
                        "summary": r.content[:200],
                        "created_at": r.created_at.isoformat(),
                        "turn_id": r.turn_id
                    })
            return result
        finally:
            self._close(db)

    # ========== 按指标关键词查询 ==========

    def search_by_metric(self, patient_id: str, metric_keyword: str,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         limit: int = 10) -> list[dict]:
        """
        按指标关键词查询用户历史记录
        例如：search_by_metric("user_123", "LDL-C") 返回所有涉及 LDL-C 的记录
        """
        db = self._get_db()
        try:
            query = db.query(EventsData).filter(
                EventsData.patient_id == patient_id,
                EventsData.event_type == "message",
                EventsData.role == "assistant"
            )
            
            if start_time:
                query = query.filter(EventsData.created_at >= start_time)
            if end_time:
                query = query.filter(EventsData.created_at <= end_time)
            
            rows = query.order_by(desc(EventsData.created_at)).limit(limit).all()
            
            result = []
            for r in rows:
                metadata = r.get_metadata() or {}
                metrics = metadata.get("metrics_involved", [])
                # 关键词匹配（支持部分匹配）
                if any(metric_keyword.lower() in m.lower() for m in metrics):
                    result.append({
                        "metrics": metrics,
                        "content": r.content,
                        "summary": r.content[:200],
                        "created_at": r.created_at.isoformat(),
                        "turn_id": r.turn_id
                    })
            return result
        finally:
            self._close(db)