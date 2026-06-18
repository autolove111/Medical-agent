"""
患者画像 Repository：patient_profile CRUD
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from harness.memory.persistence.models import PatientProfile
from harness.memory.persistence.database import get_session

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
            for key in ["name", "age", "gender", "blood_type", "height", "weight"]:
                if key in data:
                    setattr(row, key, data[key])
            for key in ["allergies", "chronic_diseases", "medications"]:
                if key in data:
                    setattr(row, key, json.dumps(data[key], ensure_ascii=False))
            for key in ["family_history", "lifestyle"]:
                if key in data:
                    setattr(row, key, json.dumps(data[key], ensure_ascii=False))
            db.commit()
        finally:
            self._close(db)

    def update(self, patient_id: str, updates: dict) -> None:
        """部分更新，只更新 updates 中有的字段"""
        self.save(patient_id, updates)
