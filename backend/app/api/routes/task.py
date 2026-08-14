"""
任务提交 API

提供 POST /ask 端点，接收用户查询，提交到 Redis 队列。
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from broker.redis_broker import submit_task, get_task_status
from api.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class AskRequest(BaseModel):
    """任务提交请求"""
    user_id: str
    session_id: str
    query: str
    task_type: str = "chat"  # "chat" 或 "report"


class AskResponse(BaseModel):
    """任务提交响应"""
    task_id: str
    status: str = "queued"


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """提交问题到任务队列。

    流程：
      1. 提交任务到 Redis 队列
      2. 绑定 task_id 到 user_id（用于后续推送）
      3. 立即返回 task_id（不等待结果）
    """
    task_id = submit_task(
        user_id=req.user_id,
        session_id=req.session_id,
        query=req.query,
        task_type=req.task_type,
    )

    # 绑定任务到用户+会话（WebSocket 推送时用）
    ws_manager.bind_task(task_id, req.user_id, req.session_id)

    logger.info("Task submitted | task_id=%s user=%s", task_id, req.user_id)
    return AskResponse(task_id=task_id)


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    """查询任务状态。"""
    status = get_task_status(task_id)
    if status is None:
        return {"error": "Task not found"}
    return status
