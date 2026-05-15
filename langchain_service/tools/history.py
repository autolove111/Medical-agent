from contextvars import ContextVar
from typing import Any, Dict, Optional
import logging
import uuid

import requests

from core.config import settings

logger = logging.getLogger(__name__)

_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)
_failed_history_user_ids = set()
_failed_age_profile_user_ids = set()


def _normalize_uuid(user_id: Optional[str]) -> Optional[str]:
    if not user_id or not isinstance(user_id, str):
        return None
    raw = user_id.strip()
    if raw in {"anonymous", "test-user-123"}:
        return None
    try:
        return str(uuid.UUID(raw))
    except Exception:
        return None


def set_current_user_id(user_id: Optional[str]) -> None:
    _current_user_id.set(_normalize_uuid(user_id))


def get_current_user_id() -> Optional[str]:
    return _current_user_id.get()


def query_user_medical_history(user_id: Optional[str]) -> str:
    effective_user_id = _normalize_uuid(user_id) or _normalize_uuid(get_current_user_id())
    if not effective_user_id:
        return "No user history available."

    if effective_user_id in _failed_history_user_ids:
        return "No prior history and no known allergy information."

    backend = getattr(settings, "BACKEND_URL", "http://localhost:8080")
    try:
        url = f"{backend}/api/v1/internal/user/medical-history"
        resp = requests.get(url, params={"userId": effective_user_id}, timeout=5)
        if resp.status_code != 200:
            if resp.status_code == 400:
                _failed_history_user_ids.add(effective_user_id)
            return "No prior history and no known allergy information."

        data = resp.json() or {}
        if data.get("status") != "success":
            return "No prior history and no known allergy information."

        med_history = data.get("medicalHistory", "None")
        drug_allergy = data.get("drugAllergy", "None")
        return f"Medical history: {med_history}\nDrug allergy: {drug_allergy}"
    except Exception as exc:
        logger.error("Query user history failed: %s", exc)
        return f"Unable to query medical history: {exc}"


def query_user_age_profile(user_id: Optional[str]) -> Dict[str, Any]:
    effective_user_id = _normalize_uuid(user_id) or _normalize_uuid(get_current_user_id())
    if not effective_user_id:
        return {}

    if effective_user_id in _failed_age_profile_user_ids:
        return {"is_pediatric": False}

    backend = getattr(settings, "BACKEND_URL", "http://localhost:8080")
    try:
        url = f"{backend}/api/v1/internal/user/profile"
        resp = requests.get(url, params={"userId": effective_user_id}, timeout=5)
        if resp.status_code != 200:
            if resp.status_code == 400:
                _failed_age_profile_user_ids.add(effective_user_id)
            return {}

        data = resp.json() or {}
        if data.get("status") != "success":
            return {}

        out: Dict[str, Any] = {}
        age_years = data.get("ageYears")
        if age_years is not None:
            try:
                out["age_years"] = float(age_years)
            except Exception:
                pass
        out["is_pediatric"] = bool(data.get("isPediatric", False))
        return out
    except Exception as exc:
        logger.error("Query user age profile failed: %s", exc)
        return {}


__all__ = [
    "get_current_user_id",
    "query_user_age_profile",
    "query_user_medical_history",
    "set_current_user_id",
]
