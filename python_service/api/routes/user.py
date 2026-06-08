"""
用户路由：画像管理、会话控制
"""

from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException

from api.models import UserProfileRequest, UserProfileResponse
from api.dependencies import get_agent_pool
from app.persistence.repositories.patient_profile_repo import PatientProfileRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user_id: str = "default"):
    """获取用户画像（优先 DB，回退 Agent 内存）"""
    repo = PatientProfileRepo()
    db_profile = repo.get(user_id)

    if db_profile is not None:
        return UserProfileResponse(
            user_id=db_profile.patient_id,
            name=db_profile.name,
            age=db_profile.age,
            gender=db_profile.gender,
            medical_history=db_profile.get_chronic_diseases(),
            allergies=db_profile.get_allergies(),
            current_medications=db_profile.get_medications(),
        )

    pool = get_agent_pool()
    agent = pool.get(user_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"用户 {user_id} 不存在，请先创建")

    u = agent.state.user
    return UserProfileResponse(
        user_id=u.user_id, name=u.name, age=u.age, gender=u.gender,
        medical_history=u.medical_history, allergies=u.allergies,
        current_medications=u.current_medications,
    )


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(request: UserProfileRequest):
    """创建或更新用户画像（DB + Agent 内存双写）"""
    repo = PatientProfileRepo()
    db_user = repo.create_or_update(
        patient_id=request.user_id,
        name=request.name,
        age=request.age,
        gender=request.gender,
        allergies=request.allergies,
        chronic_diseases=request.medical_history,
        medications=request.current_medications,
    )

    # 同步到 Agent 内存
    pool = get_agent_pool()
    agent = pool.get_or_create(
        user_id=request.user_id,
        user_name=request.name,
        user_age=request.age,
        user_gender=request.gender,
    )
    u = agent.state.user
    u.name = request.name
    u.age = request.age
    u.gender = request.gender
    u.medical_history = request.medical_history
    u.allergies = request.allergies
    u.current_medications = request.current_medications

    logger.info("Profile persisted for user=%s (DB + Agent)", request.user_id)

    return UserProfileResponse(
        user_id=db_user.patient_id,
        name=db_user.name,
        age=db_user.age,
        gender=db_user.gender,
        medical_history=request.medical_history,
        allergies=request.allergies,
        current_medications=request.current_medications,
    )


@router.post("/reset")
async def reset_session(user_id: str = "default"):
    """重置对话状态（保留用户画像）"""
    pool = get_agent_pool()
    if not pool.reset(user_id):
        raise HTTPException(status_code=404, detail=f"用户 {user_id} 不存在")

    return {"status": "ok", "message": f"用户 {user_id} 对话已重置"}


@router.get("/health")
async def health():
    """服务健康检查"""
    pool = get_agent_pool()
    db_ok = False
    try:
        PatientProfileRepo().exists("default")
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "active_users": pool.user_count,
        "database": "connected" if db_ok else "error",
        "service": "python_service",
    }


# ============================================================
# 记忆系统监控接口
# ============================================================

@router.get("/memory/stm")
async def get_stm_status(user_id: str = "default"):
    """查看用户的短期记忆（STM）实时状态"""
    from harness.memory.stm import get_active_stm

    stm = get_active_stm(user_id)
    if not stm:
        raise HTTPException(status_code=404, detail=f"用户 {user_id} 无活跃 STM 会话")

    buffer = stm.conversation_buffer
    recent = stm.get_recent_messages(n=10)

    return {
        "user_id": user_id,
        "session_id": stm.session_id,
        "buffer": {
            "message_count": len(buffer.messages),
            "summary_count": len(buffer.summaries),
            "total_tokens": buffer.total_tokens,
            "max_tokens": buffer.max_tokens,
            "usage_percent": round(buffer.total_tokens / buffer.max_tokens * 100, 1) if buffer.max_tokens else 0,
        },
        "summaries": [s.get("content", "") for s in buffer.summaries],
        "recent_messages": [
            {"role": m.get("role", ""), "content": m.get("content", "")[:200]}
            for m in recent
        ],
    }


@router.get("/memory/ltm")
async def get_ltm_status(user_id: str = "default"):
    """查看用户的长期记忆（LTM）数据"""
    from harness.memory.ltm import LTMManager

    ltm = LTMManager()

    profile = ltm.get_user_profile(user_id)
    summaries = ltm.get_summaries(user_id, limit=5)
    events = ltm.get_events(user_id, limit=10)

    return {
        "user_id": user_id,
        "profile": {
            "name": profile.name if profile else None,
            "age": profile.age if profile else None,
            "gender": profile.gender if profile else None,
            "chronic_diseases": profile.chronic_diseases if profile else [],
            "allergies": profile.allergies if profile else [],
            "medications": profile.medications if profile else [],
        } if profile else None,
        "summaries": [
            {
                "session_id": s.session_id,
                "summary": s.summary_text[:200] if s.summary_text else "",
            }
            for s in summaries
        ],
        "events": [
            {
                "event_type": e.event_type,
                "content": e.content[:200] if e.content else "",
                "session_id": e.session_id,
            }
            for e in events
        ],
    }


@router.get("/memory/sessions")
async def list_memory_sessions():
    """列出所有活跃的 STM 会话"""
    from harness.memory.stm import list_active_stms

    active = list_active_stms()
    return {
        "active_sessions": [
            {
                "user_id": uid,
                "session_id": stm.session_id,
                "message_count": len(stm.conversation_buffer.messages),
                "total_tokens": stm.conversation_buffer.total_tokens,
            }
            for uid, stm in active.items()
        ]
    }
