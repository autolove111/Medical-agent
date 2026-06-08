"""
user_profile_store.py
~~~~~~~~~~~~~~~~~~~~~
患者画像存储：PostgreSQL 实现。
"""

import logging
from typing import Optional

from ..models.user_profile import UserProfile

logger = logging.getLogger(__name__)


class UserProfileStore:
    """患者画像存储（PostgreSQL）"""

    def __init__(self, db=None):
        from app.persistence.repositories.patient_profile_repo import PatientProfileRepo
        self._repo = PatientProfileRepo(db=db)

    def get(self, patient_id: str) -> Optional[UserProfile]:
        model = self._repo.get(patient_id)
        if model is None:
            return None
        return self._repo.to_dataclass(model)

    def save(self, profile: UserProfile) -> None:
        self._repo.save_from_dataclass(profile)
        logger.debug("Saved patient profile: %s", profile.user_id)
