"""
用户路由：画像管理、会话控制（Phase 4：SQLite 持久化）
"""

from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException

from api.models import UserProfileRequest, UserProfileResponse
from api.dependencies import get_agent_pool
from app.persistence.repositories.user_repo import UserRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])


def _sync_agent_from_db(user_id: str) -> None:
    """从数据库同步用户画像到 Agent 内存"""
    pool = get_agent_pool()
    agent = pool.get(user_id)
    if agent is None:
        return

    db_user = UserRepo().get(user_id)
    if db_user is None:
        return

    import json
    u = agent.state.user
    u.name = db_user.name
    u.age = db_user.age
    u.gender = db_user.gender
    u.medical_history = json.loads(db_user.medical_history) if db_user.medical_history else []
    u.allergies = json.loads(db_user.allergies) if db_user.allergies else []
    u.current_medications = json.loads(db_user.current_medications) if db_user.current_medications else []


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user_id: str = "default"):
    """获取用户画像（优先 DB，回退 Agent 内存）"""
    repo = UserRepo()
    db_user = repo.get(user_id)

    if db_user is not None:
        import json
        return UserProfileResponse(
            user_id=db_user.id,
            name=db_user.name,
            age=db_user.age,
            gender=db_user.gender,
            medical_history=json.loads(db_user.medical_history) if db_user.medical_history else [],
            allergies=json.loads(db_user.allergies) if db_user.allergies else [],
            current_medications=json.loads(db_user.current_medications) if db_user.current_medications else [],
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
    # 写入数据库
    repo = UserRepo()
    db_user = repo.create_or_update(
        user_id=request.user_id,
        name=request.name,
        age=request.age,
        gender=request.gender,
        medical_history=request.medical_history,
        allergies=request.allergies,
        current_medications=request.current_medications,
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
        user_id=db_user.id,
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
    # 检查数据库连接
    db_ok = False
    try:
        UserRepo().exists("default")
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "active_users": pool.user_count,
        "database": "connected" if db_ok else "error",
        "service": "python_service",
    }
