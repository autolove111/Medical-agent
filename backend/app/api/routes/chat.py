"""
聊天路由

所有请求提交到 Redis 队列，由 Worker 处理。
SSE 端点通过 Pub/Sub 实时推送结果。

提供：
  - GET  /api/chat/react-stream  SSE 流式对话
  - POST /api/chat/react         非流式对话
  - GET  /api/chat/history       对话历史
"""

from __future__ import annotations
import json
import logging
import asyncio
import threading

import redis
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse

from broker.redis_broker import submit_task, TASK_STREAM_PREFIX
from core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


def _get_redis():
    return redis.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None, decode_responses=True,
    )


@router.get("/chat/react-stream")
async def chat_react_stream(
    user_id: str = Query(..., description="用户 ID"),
    session_id: str = Query(..., description="会话 ID"),
    message: str = Query(..., min_length=1, description="用户消息"),
):
    """SSE 流式对话 — 提交到队列，通过 Pub/Sub 推送结果"""

    # 1. 提交任务到队列
    task_id = submit_task(user_id, session_id, message)
    logger.info("Task submitted via HTTP SSE | task_id=%s", task_id)

    # 2. 订阅该任务的 Pub/Sub 频道
    channel = f"{TASK_STREAM_PREFIX}{task_id}"
    r = _get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(channel)

    async def event_generator():
        try:
            # 先发 task_id
            yield f"data: {json.dumps({'type': 'task_accepted', 'task_id': task_id}, ensure_ascii=False)}\n\n"

            loop = asyncio.get_event_loop()
            timeout_count = 0
            max_timeouts = 600  # 5 分钟 (600 * 500ms)

            while timeout_count < max_timeouts:
                # 在线程中阻塞读取 Pub/Sub 消息
                message = await loop.run_in_executor(
                    None, lambda: pubsub.get_message(timeout=0.5)
                )

                if message is None:
                    timeout_count += 1
                    if timeout_count % 20 == 0:  # 每 10 秒发一次心跳
                        yield ": heartbeat\n\n"
                    continue

                if message["type"] != "message":
                    continue

                timeout_count = 0
                data = json.loads(message["data"])
                msg_type = data.get("type", "")

                # 转发给前端
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                # 最终答案或失败 → 结束
                if msg_type in ("final_answer", "task_result", "error"):
                    break

        except Exception as e:
            logger.error("SSE error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()
            r.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/react")
async def chat_react(
    user_id: str = Query(..., description="用户 ID"),
    session_id: str = Query(..., description="会话 ID"),
    message: str = Query(..., min_length=1, description="用户消息"),
):
    """非流式对话 — 提交到队列，等待最终结果"""
    task_id = submit_task(user_id, session_id, message)
    logger.info("Task submitted via HTTP | task_id=%s", task_id)

    channel = f"{TASK_STREAM_PREFIX}{task_id}"
    r = _get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(channel)

    try:
        loop = asyncio.get_event_loop()
        timeout_count = 0
        max_timeouts = 600

        while timeout_count < max_timeouts:
            message = await loop.run_in_executor(
                None, lambda: pubsub.get_message(timeout=0.5)
            )
            if message is None:
                timeout_count += 1
                continue
            if message["type"] != "message":
                continue

            data = json.loads(message["data"])
            msg_type = data.get("type", "")

            if msg_type == "final_answer":
                return {"result": data.get("answer", ""), "task_id": task_id}
            elif msg_type in ("task_result", "error"):
                return {"error": data.get("error", "未知错误"), "task_id": task_id}

        raise HTTPException(status_code=504, detail="处理超时")
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
        r.close()


@router.get("/chat/history")
async def chat_history(
    user_id: str = Query(..., description="用户 ID"),
    session_id: str = Query(..., description="会话 ID"),
):
    """获取对话历史（从 Redis 短期记忆读取）"""
    try:
        from memory.short_memory.store import ShortMemoryStore
        stm = ShortMemoryStore(user_id=user_id, session_id=session_id)
        return {"data": {"messages": stm.messages}}
    except Exception as e:
        logger.error("Chat history failed: %s", e, exc_info=True)
        return {"data": {"messages": []}}
