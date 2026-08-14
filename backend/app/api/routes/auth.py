"""
认证路由：兼容旧前端 /api/v1/auth/* 接口
"""

from __future__ import annotations
import hashlib
import hmac
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_session
from app.models.schemas import UserAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_TOKEN_SECRET = secrets.token_hex(32)
_TOKEN_TTL = 86400 * 7


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"medagent:{password}".encode()).hexdigest()


def _make_token(user_id: str) -> str:
    payload = f"{user_id}:{int(time.time())}"
    sig = hmac.new(_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def _verify_token(token: str) -> str | None:
    try:
        parts = token.rsplit(":", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = hmac.new(_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        user_id, ts = payload.split(":", 1)
        if int(ts) + _TOKEN_TTL < time.time():
            return None
        return user_id
    except Exception:
        return None


class LoginRequest(BaseModel):
    idNumber: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    realName: str = Field(..., min_length=1)
    idNumber: str = Field(..., min_length=1)
    age: int = Field(..., ge=0, le=150)
    password: str = Field(..., min_length=6)
    confirmPassword: str = Field(..., min_length=6)


@router.post("/register")
async def register(req: RegisterRequest):
    if req.password != req.confirmPassword:
        raise HTTPException(status_code=400, detail="两次密码不一致")

    db = get_session()
    try:
        # 检查用户是否已存在
        existing = db.query(UserAccount).filter(
            UserAccount.patient_id == req.idNumber
        ).first()
        if existing is not None:
            raise HTTPException(status_code=400, detail="该身份证号已注册")

        # 创建新用户
        new_user = UserAccount(
            patient_id=req.idNumber,
            name=req.realName,
            age=req.age,
            password_hash=_hash_password(req.password),
        )
        db.add(new_user)
        db.commit()
    finally:
        db.close()

    token = _make_token(req.idNumber)
    return {
        "code": 200, "message": "success",
        "data": {
            "token": token,
            "user": {"idNumber": req.idNumber, "realName": req.realName, "age": req.age},
        },
    }


@router.post("/login")
async def login(req: LoginRequest):
    db = get_session()
    try:
        user = db.query(UserAccount).filter(
            UserAccount.patient_id == req.idNumber
        ).first()
        if user is None:
            raise HTTPException(status_code=401, detail="身份证号或密码错误")

        stored_hash = user.password_hash if user else ""
    finally:
        db.close()

    if not stored_hash or stored_hash != _hash_password(req.password):
        raise HTTPException(status_code=401, detail="身份证号或密码错误")

    token = _make_token(req.idNumber)
    return {
        "code": 200, "message": "success",
        "data": {
            "token": token,
            "user": {
                "idNumber": req.idNumber,
                "realName": user.name if user else req.idNumber,
                "age": user.age if user else 0,
            },
        },
    }


@router.get("/me")
async def get_me(token: str = ""):
    user_id = _verify_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")

    db = get_session()
    try:
        user = db.query(UserAccount).filter(
            UserAccount.patient_id == user_id
        ).first()
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
    finally:
        db.close()

    return {
        "code": 200, "message": "success",
        "data": {
            "user": {
                "idNumber": user.patient_id,
                "realName": user.name,
                "age": user.age,
            }
        },
    }
