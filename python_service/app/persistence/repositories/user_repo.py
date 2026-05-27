"""
用户 Repository：用户画像 CRUD
"""

from __future__ import annotations
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.persistence.models import UserModel
from app.persistence.database import get_session

logger = logging.getLogger(__name__)


class UserRepo:
    """用户数据访问层"""

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

    def create_or_update(
        self,
        user_id: str,
        name: str = "",
        age: int = 0,
        gender: str = "",
        medical_history: list[str] | None = None,
        allergies: list[str] | None = None,
        current_medications: list[str] | None = None,
    ) -> UserModel:
        db = self._get_db()
        try:
            user = db.query(UserModel).filter(UserModel.id == user_id).first()
            if user is None:
                user = UserModel(id=user_id)
                db.add(user)
                logger.info("Creating user: %s", user_id)

            user.name = name or user.name
            user.age = age or user.age
            user.gender = gender or user.gender
            user.medical_history = json.dumps(medical_history or [], ensure_ascii=False)
            user.allergies = json.dumps(allergies or [], ensure_ascii=False)
            user.current_medications = json.dumps(current_medications or [], ensure_ascii=False)

            db.commit()
            db.refresh(user)
            return user
        finally:
            self._close_if_own(db)

    def get(self, user_id: str) -> Optional[UserModel]:
        db = self._get_db()
        try:
            return db.query(UserModel).filter(UserModel.id == user_id).first()
        finally:
            self._close_if_own(db)

    def delete(self, user_id: str) -> bool:
        db = self._get_db()
        try:
            user = db.query(UserModel).filter(UserModel.id == user_id).first()
            if user is None:
                return False
            db.delete(user)
            db.commit()
            return True
        finally:
            self._close_if_own(db)

    def exists(self, user_id: str) -> bool:
        db = self._get_db()
        try:
            return db.query(UserModel.id).filter(UserModel.id == user_id).first() is not None
        finally:
            self._close_if_own(db)
