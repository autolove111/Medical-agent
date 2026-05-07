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
    if raw in {"当前用户", "无用户ID", "anonymous", "test-user-123"}:
        return None
    try:
        return str(uuid.UUID(raw))
    except Exception:
        return None


def set_current_user_id(user_id: Optional[str]):
    _current_user_id.set(_normalize_uuid(user_id))


def get_current_user_id() -> Optional[str]:
    return _current_user_id.get()


def query_user_medical_history(user_id: Optional[str]) -> str:
    explicit_user_id = _normalize_uuid(user_id)
    context_user_id = _normalize_uuid(get_current_user_id())
    effective_user_id = explicit_user_id or context_user_id
    if not effective_user_id:
        return "【用户信息】当前为匿名访问模式，无法查询用户既往史。建议登录后重试以获取个性化建议。"

    if effective_user_id in _failed_history_user_ids:
        return "【既往史】暂无病历记录\n【过敏信息】无已知过敏史"

    backend = getattr(settings, "BACKEND_URL", "http://localhost:8080")
    try:
        logger.info("[TOOLS][History] start | user_id=%s", effective_user_id)
        url = f"{backend}/api/v1/internal/user/medical-history"
        resp = requests.get(url, params={"userId": effective_user_id}, timeout=5)
        if resp.status_code != 200:
            logger.warning("后端返回非 200: %s %s", resp.status_code, resp.text)
            if resp.status_code == 400:
                _failed_history_user_ids.add(effective_user_id)
            return "【既往史】暂无病历记录\n【过敏信息】无已知过敏史"
        data = resp.json()
        if data.get("status") == "success":
            med_history = data.get("medicalHistory", "无")
            drug_allergy = data.get("drugAllergy", "无")
            logger.info(
                "[TOOLS][History] done | user_id=%s med_len=%d allergy_len=%d",
                effective_user_id,
                len(str(med_history or "")),
                len(str(drug_allergy or "")),
            )
            return f"【既往史】{med_history}\n【过敏信息】{drug_allergy}"
        return f"【后端错误】{data.get('message', '未知错误')}"
    except Exception as e:
        logger.error("查询用户病历异常: %s", e)
        return f"【系统异常】无法查询病历: {str(e)}"


def query_user_age_profile(user_id: Optional[str]) -> Dict[str, Any]:
    explicit_user_id = _normalize_uuid(user_id)
    context_user_id = _normalize_uuid(get_current_user_id())
    effective_user_id = explicit_user_id or context_user_id
    if not effective_user_id:
        return {}

    if effective_user_id in _failed_age_profile_user_ids:
        return {"is_pediatric": False}

    backend = getattr(settings, "BACKEND_URL", "http://localhost:8080")
    try:
        url = f"{backend}/api/v1/internal/user/profile"
        resp = requests.get(url, params={"userId": effective_user_id}, timeout=5)
        if resp.status_code != 200:
            logger.warning("年龄画像接口返回非 200: %s %s", resp.status_code, resp.text)
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
    except Exception as e:
        logger.error("查询用户年龄画像异常: %s", e)
        return {}


__all__ = [
    "get_current_user_id",
    "query_user_age_profile",
    "query_user_medical_history",
    "set_current_user_id",
]

