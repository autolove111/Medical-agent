"""
WebSocket 端点 + 消息推送后台任务

提供：
  - WS /ws/{user_id}  —— 用户 WebSocket 连接
  - start_push_worker() —— 后台订阅 Redis Pub/Sub，推送给 WebSocket
"""

import asyncio
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws_manager import ws_manager
from broker.redis_broker import subscribe_result, TASK_RESULT_CHANNEL

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# WebSocket 端点
# ============================================================

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(ws: WebSocket, user_id: str):
    """用户 WebSocket 连接。

    前端连接：ws://localhost:8001/ws/{user_id}
    接收消息格式：{"type": "ask", "query": "...", "session_id": "..."}
    """
    await ws_manager.connect(user_id, ws)

    try:
        while True:
            data = await ws.receive_text()

            if data == "ping":
                await ws.send_json({"type": "pong"})
                continue

            # 解析 JSON 消息
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("WS invalid JSON | user=%s", user_id)
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ask":
                # 用户提问 → 提交任务到队列
                query = msg.get("query", "").strip()
                session_id = msg.get("session_id", "default")
                task_type = msg.get("task_type", "chat")

                if not query:
                    continue

                from broker.redis_broker import submit_task
                task_id = submit_task(user_id, session_id, query, task_type)
                ws_manager.bind_task(task_id, user_id, session_id)

                logger.info("Task submitted via WS | task_id=%s user=%s query=%s", task_id, user_id, query[:50])

                # 回复前端：任务已接收
                await ws.send_json({"type": "task_accepted", "task_id": task_id})

            else:
                logger.debug("WS unknown type | user=%s type=%s", user_id, msg_type)

    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, ws)
    except Exception as exc:
        logger.error("WS error | user=%s error=%s", user_id, exc)
        ws_manager.disconnect(user_id, ws)


# ============================================================
# 消息推送后台任务
# ============================================================

async def push_worker():
    """后台任务：订阅 Redis Pub/Sub 频道，推送给对应 WebSocket。

    在 FastAPI lifespan 中启动。
    所有消息都通过 Pub/Sub 传递，简单统一。
    """
    import redis as redis_lib
    import json
    from core.config import settings as app_settings
    from broker.redis_broker import TASK_STREAM_PREFIX
    logger.info("Push worker started, subscribing to stream channels via Pub/Sub")

    # 复用一个 Redis 连接
    r = redis_lib.Redis(
        host=app_settings.REDIS_HOST,
        port=app_settings.REDIS_PORT,
        password=app_settings.REDIS_PASSWORD or None,
        decode_responses=True,
    )

    # 用于跟踪已订阅的 task 频道
    subscribed_tasks = set()
    pubsub = r.pubsub()

    try:
        while True:
            # ── 1. 订阅活跃任务的流式频道 ──
            current_tasks = set(ws_manager.task_owners.keys())
            for task_id in current_tasks:
                if task_id not in subscribed_tasks:
                    channel = f"{TASK_STREAM_PREFIX}{task_id}"
                    pubsub.subscribe(channel)
                    subscribed_tasks.add(task_id)
                    logger.info("Subscribed to stream | task_id=%s", task_id)

            # ── 2. 批量处理所有 Pub/Sub 消息 ──
            while True:
                message = pubsub.get_message(timeout=0.01)
                if message is None:
                    break
                if message["type"] != "message":
                    continue

                channel = message["channel"]
                if TASK_STREAM_PREFIX not in channel:
                    continue

                task_id = channel.replace(TASK_STREAM_PREFIX, "")
                msg = json.loads(message["data"])

                owner = ws_manager.get_task_owner(task_id)
                user_id = owner["user_id"] if owner else None
                if not user_id:
                    continue

                msg_type = msg.get("type", "")

                # 推送消息给前端
                if msg_type == "final_answer":
                    await ws_manager.send_to_user(user_id, {
                        "type": "final_answer",
                        "task_id": task_id,
                        "answer": msg.get("answer", ""),
                    })
                    ws_manager.unbind_task(task_id)
                    logger.info("Final answer pushed | task_id=%s", task_id)
                elif msg_type == "task_result":
                    await ws_manager.send_to_user(user_id, {
                        "type": "task_result",
                        "task_id": task_id,
                        "status": msg.get("status", "failed"),
                        "error": msg.get("error", ""),
                    })
                    ws_manager.unbind_task(task_id)
                    logger.info("Task result pushed | task_id=%s", task_id)
                else:
                    await ws_manager.send_to_user(user_id, msg)
                    logger.debug("Stream chunk pushed | task_id=%s type=%s", task_id, msg_type)

            # ── 3. 清理已完成任务的订阅 ──
            stale_tasks = subscribed_tasks - set(ws_manager.task_owners.keys())
            for task_id in stale_tasks:
                channel = f"{TASK_STREAM_PREFIX}{task_id}"
                try:
                    pubsub.unsubscribe(channel)
                except Exception:
                    pass
                subscribed_tasks.discard(task_id)

            await asyncio.sleep(0.05)

    except asyncio.CancelledError:
        logger.info("Push worker cancelled")
    except Exception as exc:
        logger.error("Push worker error: %s", exc, exc_info=True)
    finally:
        pubsub.close()
