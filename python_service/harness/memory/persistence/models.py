"""
ORM 模型：3 张表

1. patient_profile         — 患者画像（全局共享，每人一条）
2. session_data            — 统一会话表（对话消息 + 时间轴事件 + 会话总结）
3. working_memory_snapshot — 工作记忆快照（每轮对话一份）
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, DateTime

from app.persistence.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


# ============================================================
# 1. 患者画像
# ============================================================

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


# ============================================================
# 2. 统一会话数据
# ============================================================

class EventsData(Base):
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
    event_type = Column(String(32), nullable=False, index=True,
                        comment="message / lab_result / symptom / summary")
    role = Column(String(16), default="", comment="user / assistant（仅 message）")
    turn_id = Column(Integer, default=0, comment="对话轮次（仅 message）")
    content = Column(Text, default="", comment="内容文本")
    raw_data = Column(Text, default="{}", comment="原始数据 JSON（化验报告指标等）")
    weight = Column(Float, default=1.0, comment="权重，召回时递增，用于遗忘机制")
    medical = Column(Float, default=0.0, comment="医疗信息价值评分")
    experience = Column(Float, default=0.0, comment="经验总结价值评分")
    profile = Column(Float, default=0.0, comment="画像更新价值评分")
    created_at = Column(DateTime, default=_utcnow, index=True)

    def get_raw_data(self) -> dict:
        return json.loads(self.raw_data) if self.raw_data else {}

    def set_raw_data(self, data: dict):
        self.raw_data = json.dumps(data, ensure_ascii=False)


# ============================================================
# 3. 工作记忆快照
# ============================================================

class WorkingMemorySnapshot(Base):
    """
    工作记忆快照 — 每轮对话结束时保存

    记录该轮工作记忆的完整状态。
    """
    __tablename__ = "working_memory_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(64), nullable=False, index=True, comment="患者 ID")
    session_id = Column(String(128), nullable=False, index=True, comment="会话 ID")
    turn_id = Column(Integer, nullable=False, comment="对话轮次")
    state_snapshot = Column(Text, default="{}", comment="工作记忆状态 JSON")
    created_at = Column(DateTime, default=_utcnow, index=True)

    def get_state_snapshot(self) -> dict:
        return json.loads(self.state_snapshot) if self.state_snapshot else {}

    def set_state_snapshot(self, data: dict):
        self.state_snapshot = json.dumps(data, ensure_ascii=False)


# ============================================================
# 4. 短期记忆快照
# ============================================================

class MemorySnapshot(Base):
    """记忆快照 — 存储 messages / summary / message_len"""
    __tablename__ = "short_memory_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(64), nullable=False, index=True, comment="患者 ID")
    session_id = Column(String(128), nullable=False, index=True, comment="会话 ID")
    messages = Column(Text, default="[]", comment="消息列表 JSON")
    summary = Column(Text, default="[]", comment="摘要列表 JSON")
    message_len = Column(Integer, default=0, comment="消息总字符数")
    created_at = Column(DateTime, default=_utcnow, index=True)

    def get_messages(self) -> list[dict]:
        return json.loads(self.messages) if self.messages else []

    def set_messages(self, data: list[dict]):
        self.messages = json.dumps(data, ensure_ascii=False)

    def get_summary(self) -> list[dict]:
        return json.loads(self.summary) if self.summary else []

    def set_summary(self, data: list[dict]):
        self.summary = json.dumps(data, ensure_ascii=False)



