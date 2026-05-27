"""
ORM 模型：User / Report / ChatMessage

三张核心表覆盖用户画像、化验报告、对话历史。
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.persistence.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class UserModel(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, comment="用户 ID")
    name = Column(String(128), default="", comment="姓名")
    age = Column(Integer, default=0, comment="年龄")
    gender = Column(String(8), default="", comment="性别：男/女")
    password_hash = Column(String(128), default="", comment="密码哈希")
    medical_history = Column(Text, default="[]", comment="既往病史 JSON")
    allergies = Column(Text, default="[]", comment="过敏史 JSON")
    current_medications = Column(Text, default="[]", comment="当前用药 JSON")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # 关联
    reports = relationship("ReportModel", back_populates="user", cascade="all, delete-orphan")
    chats = relationship("ChatMessageModel", back_populates="user", cascade="all, delete-orphan")


class ReportModel(Base):
    """化验报告表"""
    __tablename__ = "reports"

    id = Column(String(128), primary_key=True, comment="报告 ID (rpt_xxx)")
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    report_date = Column(String(32), default="", comment="检验日期 YYYY-MM-DD")
    file_path = Column(String(512), default="", comment="原始文件路径")
    total_count = Column(Integer, default=0)
    abnormal_count = Column(Integer, default=0)
    normal_count = Column(Integer, default=0)
    has_critical = Column(Integer, default=0, comment="0/1")
    indicators_json = Column(Text, default="[]", comment="LabIndicator JSON 数组")
    raw_ocr_text = Column(Text, default="")
    correlation_json = Column(Text, default="[]", comment="联动分析结果 JSON")
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("UserModel", back_populates="reports")

    def get_indicators(self) -> list[dict]:
        return json.loads(self.indicators_json) if self.indicators_json else []

    def set_indicators(self, indicators: list[dict]):
        self.indicators_json = json.dumps(indicators, ensure_ascii=False)

    def get_correlations(self) -> list[dict]:
        return json.loads(self.correlation_json) if self.correlation_json else []

    def set_correlations(self, correlations: list[dict]):
        self.correlation_json = json.dumps(correlations, ensure_ascii=False)

    def to_summary(self) -> dict:
        return {
            "report_id": self.id,
            "report_date": self.report_date,
            "total_count": self.total_count,
            "abnormal_count": self.abnormal_count,
            "normal_count": self.normal_count,
            "has_critical": bool(self.has_critical),
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class ChatMessageModel(Base):
    """对话历史表（可选持久化，用于模块四 P2 用户系统）"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(128), default="", comment="关联报告 ID（可为空）")
    role = Column(String(16), nullable=False, comment="user / assistant / system / tool")
    content = Column(Text, default="")
    sources_json = Column(Text, default="[]", comment="来源引用 JSON")
    turn_number = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("UserModel", back_populates="chats")

    def get_sources(self) -> list[dict]:
        return json.loads(self.sources_json) if self.sources_json else []
