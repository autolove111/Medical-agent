"""
记忆路由

提供 /memory/save、/memory/load 端点。
直接操作 Redis 短期记忆，不依赖 SessionPool。
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


def _get_memory(user_id: str, session_id: str):
    from memory import MemorySystem
    memory = MemorySystem(user_id, session_id)
    memory.load_snapshot()
    return memory


@router.post("/save")
async def memory_save(user_id: str, session_id: str, message: str, role: str = "user"):
    """保存消息到记忆"""
    try:
        memory = _get_memory(user_id, session_id)
        if role == "user":
            memory.on_user_message(message)
        else:
            memory.on_assistant_message(message)
        return {"status": "saved"}
    except Exception as e:
        logger.error("Memory save failed: %s", e, exc_info=True)
        return {"error": str(e)}


@router.get("/load")
async def memory_load(user_id: str, session_id: str):
    """加载记忆"""
    try:
        memory = _get_memory(user_id, session_id)
        return {
            "messages": memory.get_short_memory_text(),
            "summary": memory.get_summary_text(),
            "profile": memory.get_profile_text(),
        }
    except Exception as e:
        logger.error("Memory load failed: %s", e, exc_info=True)
        return {"error": str(e)}
