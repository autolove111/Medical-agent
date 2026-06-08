"""
患者画像 Repository：patient_profile CRUD + ORM ↔ dataclass 转换
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.persistence.models import PatientProfile
from app.persistence.database import get_session

logger = logging.getLogger(__name__)


class PatientProfileRepo:
    """患者画像数据访问层"""

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

    # ---- CRUD ----

    def get(self, patient_id: str) -> Optional[PatientProfile]:
        db = self._get_db()
        try:
            return db.query(PatientProfile).filter(PatientProfile.patient_id == patient_id).first()
        finally:
            self._close_if_own(db)

    def create_or_update(
        self,
        patient_id: str,
        name: str = "",
        age: int = 0,
        gender: str = "",
        blood_type: str = "",
        height: float = 0.0,
        weight: float = 0.0,
        allergies: list[str] = None,
        chronic_diseases: list[str] = None,
        medications: list[str] = None,
        family_history: dict = None,
        lifestyle: dict = None,
    ) -> PatientProfile:
        db = self._get_db()
        try:
            profile = db.query(PatientProfile).filter(PatientProfile.patient_id == patient_id).first()
            if profile is None:
                profile = PatientProfile(patient_id=patient_id)
                db.add(profile)
                logger.info("Creating patient profile: %s", patient_id)

            if name:
                profile.name = name
            if age:
                profile.age = age
            if gender:
                profile.gender = gender
            if blood_type:
                profile.blood_type = blood_type
            if height:
                profile.height = height
            if weight:
                profile.weight = weight
            if allergies is not None:
                profile.allergies = json.dumps(allergies, ensure_ascii=False)
            if chronic_diseases is not None:
                profile.chronic_diseases = json.dumps(chronic_diseases, ensure_ascii=False)
            if medications is not None:
                profile.medications = json.dumps(medications, ensure_ascii=False)
            if family_history is not None:
                profile.family_history = json.dumps(family_history, ensure_ascii=False)
            if lifestyle is not None:
                profile.lifestyle = json.dumps(lifestyle, ensure_ascii=False)

            db.commit()
            db.refresh(profile)
            return profile
        finally:
            self._close_if_own(db)

    def delete(self, patient_id: str) -> bool:
        db = self._get_db()
        try:
            profile = db.query(PatientProfile).filter(PatientProfile.patient_id == patient_id).first()
            if profile is None:
                return False
            db.delete(profile)
            db.commit()
            return True
        finally:
            self._close_if_own(db)

    def exists(self, patient_id: str) -> bool:
        db = self._get_db()
        try:
            return db.query(PatientProfile.patient_id).filter(
                PatientProfile.patient_id == patient_id
            ).first() is not None
        finally:
            self._close_if_own(db)

    # ---- ORM ↔ dataclass 转换 ----

    @staticmethod
    def to_dataclass(model: PatientProfile):
        """ORM → memory UserProfile dataclass"""
        from harness.memory.models.user_profile import UserProfile
        return UserProfile(
            user_id=model.patient_id,
            name=model.name or "",
            age=model.age or 0,
            gender=model.gender or "",
            blood_type=model.blood_type or "",
            height=model.height or 0.0,
            weight=model.weight or 0.0,
            chronic_diseases=model.get_chronic_diseases(),
            allergies=model.get_allergies(),
            medications=model.get_medications(),
            family_history=model.get_family_history(),
            lifestyle=model.get_lifestyle(),
        )

    def save_from_dataclass(self, profile) -> PatientProfile:
        """memory UserProfile dataclass → 写入 DB"""
        return self.create_or_update(
            patient_id=profile.user_id,
            name=profile.name,
            age=profile.age,
            gender=profile.gender,
            blood_type=profile.blood_type,
            height=profile.height,
            weight=profile.weight,
            allergies=profile.allergies,
            chronic_diseases=profile.chronic_diseases,
            medications=profile.medications,
            family_history=profile.family_history,
            lifestyle=profile.lifestyle,
        )
