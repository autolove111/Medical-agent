"""
患者画像 Repository：patient_profile CRUD
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from memory.persistence.models import PatientProfile
from memory.persistence.database import get_session

logger = logging.getLogger(__name__)


class ProfileRepo:

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._own = db is None

    def _get_db(self) -> Session:
        return self._db if self._db is not None else get_session()

    def _close(self, db: Session):
        if self._own:
            db.close()

    def get(self, patient_id: str) -> Optional[dict]:
        db = self._get_db()
        try:
            row = db.query(PatientProfile).filter(
                PatientProfile.patient_id == patient_id
            ).first()
            if not row:
                return None
            return {
                "patient_id": row.patient_id,
                "name": row.name,
                "age": row.age,
                "gender": row.gender,
                "blood_type": row.blood_type,
                "height": row.height,
                "weight": row.weight,
                "allergies": row.get_allergies(),
                "chronic_diseases": row.get_chronic_diseases(),
                "medications": row.get_medications(),
                "family_history": row.get_family_history(),
                "lifestyle": row.get_lifestyle(),
            }
        finally:
            self._close(db)

    def save(self, patient_id: str, data: dict) -> None:
        db = self._get_db()
        try:
            row = db.query(PatientProfile).filter(
                PatientProfile.patient_id == patient_id
            ).first()
            if row is None:
                row = PatientProfile(patient_id=patient_id)
                db.add(row)

            # 标量字段：直接覆盖
            for key in ["name", "age", "gender", "blood_type", "height", "weight"]:
                if key in data:
                    setattr(row, key, data[key])

            # 列表字段：合并去重（不覆盖）
            for key in ["allergies", "chronic_diseases", "medications"]:
                if key in data and data[key]:
                    existing = json.loads(getattr(row, key) or "[]")
                    new_items = data[key] if isinstance(data[key], list) else [data[key]]
                    merged = list(set(existing + new_items))
                    setattr(row, key, json.dumps(merged, ensure_ascii=False))

            # 字典字段：合并键值（不覆盖）
            for key in ["family_history", "lifestyle"]:
                if key in data and data[key]:
                    existing = json.loads(getattr(row, key) or "{}")
                    if isinstance(data[key], dict):
                        existing.update(data[key])
                    setattr(row, key, json.dumps(existing, ensure_ascii=False))

            db.commit()
        finally:
            self._close(db)

    def update(self, patient_id: str, updates: dict) -> None:
        """部分更新，只更新 updates 中有的字段"""
        self.save(patient_id, updates)
