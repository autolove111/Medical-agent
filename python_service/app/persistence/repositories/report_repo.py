"""
报告 Repository：化验报告 CRUD
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.persistence.models import ReportModel
from app.persistence.database import get_session

logger = logging.getLogger(__name__)


class ReportRepo:
    """报告数据访问层"""

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

    def save(
        self,
        report_id: str,
        user_id: str,
        report_date: str,
        file_path: str,
        total_count: int,
        abnormal_count: int,
        normal_count: int,
        has_critical: bool,
        indicators: list[dict],
        correlations: list[dict] | None = None,
        raw_ocr_text: str = "",
    ) -> ReportModel:
        db = self._get_db()
        try:
            report = ReportModel(
                id=report_id,
                user_id=user_id,
                report_date=report_date,
                file_path=file_path,
                total_count=total_count,
                abnormal_count=abnormal_count,
                normal_count=normal_count,
                has_critical=1 if has_critical else 0,
                raw_ocr_text=raw_ocr_text,
            )
            report.set_indicators(indicators)
            report.set_correlations(correlations or [])
            db.add(report)
            db.commit()
            db.refresh(report)
            logger.info("Report saved: %s (%d indicators)", report_id, total_count)
            return report
        finally:
            self._close(db)

    def get(self, report_id: str) -> Optional[ReportModel]:
        db = self._get_db()
        try:
            return db.query(ReportModel).filter(ReportModel.id == report_id).first()
        finally:
            self._close(db)

    def get_full(self, report_id: str) -> Optional[dict]:
        """获取完整报告（含解析后的指标和联动分析）"""
        report = self.get(report_id)
        if report is None:
            return None
        return {
            "report_id": report.id,
            "user_id": report.user_id,
            "report_date": report.report_date,
            "file_path": report.file_path,
            "total_count": report.total_count,
            "abnormal_count": report.abnormal_count,
            "normal_count": report.normal_count,
            "has_critical": bool(report.has_critical),
            "indicators": report.get_indicators(),
            "correlations": report.get_correlations(),
            "raw_ocr_text": report.raw_ocr_text,
            "created_at": report.created_at.isoformat() if report.created_at else "",
        }

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        db = self._get_db()
        try:
            reports = (
                db.query(ReportModel)
                .filter(ReportModel.user_id == user_id)
                .order_by(desc(ReportModel.created_at))
                .limit(limit)
                .all()
            )
            return [r.to_summary() for r in reports]
        finally:
            self._close(db)

    def delete(self, report_id: str) -> bool:
        db = self._get_db()
        try:
            report = db.query(ReportModel).filter(ReportModel.id == report_id).first()
            if report is None:
                return False
            db.delete(report)
            db.commit()
            return True
        finally:
            self._close(db)
