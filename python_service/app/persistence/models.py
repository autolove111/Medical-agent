"""
ORM 模型：2 张核心表

1. patient_profile  — 患者画像（全局共享，每人一条）
2. session_data     — 统一会话表（对话消息 + 时间轴事件 + 会话总结）
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, DateTime

from app.persistence.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class PatientProfile(Base):
    """患者画像表 — 全局共享，每个患者一条记录"""
    __tablename__ = "patient_profile"

    patient_id = Column(String(64), primary_key=True, comment="患者 ID")
    name = Column(String(128), default="", comment="姓名")
    age = Column(Integer, default=0, comment="年龄")
    gender = Column(String(8), default="", comment="性别：男/女")
    password_hash = Column(String(128), default="", comment="密码哈希")
    blood_type = Column(String(8), default="", comment="血型")
    height = Column(Float, default=0.0, comment="身高 cm")
    weight = Column(Float, default=0.0, comment="体重 kg")
    allergies = Column(Text, default="[]", comment="过敏史 JSON")
    chronic_diseases = Column(Text, default="[]", comment="慢性病 JSON")
    medications = Column(Text, default="[]", comment="当前用药 JSON")
    family_history = Column(Text, default="{}", comment="家族史 JSON")
    lifestyle = Column(Text, default="{}", comment="生活方式 JSON")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # ---- JSON 字段辅助方法 ----

    def get_allergies(self) -> list[str]:
        return json.loads(self.allergies) if self.allergies else []

    def get_chronic_diseases(self) -> list[str]:
        return json.loads(self.chronic_diseases) if self.chronic_diseases else []

    def get_medications(self) -> list[str]:
        return json.loads(self.medications) if self.medications else []

    def get_family_history(self) -> dict:
        return json.loads(self.family_history) if self.family_history else {}

    def get_lifestyle(self) -> dict:
        return json.loads(self.lifestyle) if self.lifestyle else {}


class SessionData(Base):
    """
    统一会话表 — 一个会话的所有数据都在这张表里

    event_type 取值：
    - 'message'    : 对话消息（role + turn_id 有值）
    - 'lab_result' : 化验结果事件（raw_data 含完整报告）
    - 'symptom'    : 症状事件
    - 'summary'    : 会话总结（每个会话一条）
    """
    __tablename__ = "session_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(64), nullable=False, index=True, comment="患者 ID")
    session_id = Column(String(128), nullable=False, index=True, comment="会话 ID")
    event_type = Column(String(32), nullable=False, index=True,
                        comment="message / lab_result / symptom / summary")
    role = Column(String(16), default="", comment="user / assistant（仅 message）")
    turn_id = Column(Integer, default=0, comment="对话轮次（仅 message）")
    content = Column(Text, default="", comment="内容文本")
    raw_data = Column(Text, default="{}", comment="原始数据 JSON（化验报告指标等）")
    created_at = Column(DateTime, default=_utcnow, index=True)

    # ---- 辅助方法 ----

    def get_raw_data(self) -> dict:
        return json.loads(self.raw_data) if self.raw_data else {}

    def set_raw_data(self, data: dict):
        self.raw_data = json.dumps(data, ensure_ascii=False)
