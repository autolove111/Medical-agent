"""
WebSocket 连接管理器

职责：
  - 注册/注销 WebSocket 连接
  - 按 user_id 查找连接
  - 心跳检测
  - 离线消息缓存
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    """WebSocket 连接管理器（全局单例）。

    数据结构：
      connections: {user_id: {ws1, ws2, ...}}   # 一个用户可能有多个标签页
      task_owners: {task_id: user_id}            # 任务归属映射
      offline_cache: {user_id: [msg1, msg2, ...]}  # 离线消息缓存
    """

    def __init__(self):
        # user_id → set of WebSocket connections
        self.connections: Dict[str, Set[WebSocket]] = {}
        # task_id → user_id（任务提交时绑定）
        self.task_owners: Dict[str, str] = {}
        # user_id → list of messages（用户离线时缓存）
        self.offline_cache: Dict[str, list] = {}
        # 心跳超时（秒）
        self.heartbeat_timeout = 60

    # ── 连接管理 ──

    async def connect(self, user_id: str, ws: WebSocket):
        """注册新连接。"""
        await ws.accept()

        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(ws)

        logger.info("WS connected | user=%s total=%d", user_id, len(self.connections[user_id]))

        # 推送离线缓存
        if user_id in self.offline_cache:
            cached = self.offline_cache.pop(user_id)
            for msg in cached:
                await ws.send_json(msg)
            logger.info("Flushed %d offline messages | user=%s", len(cached), user_id)

    def disconnect(self, user_id: str, ws: WebSocket):
        """注销连接。"""
        if user_id in self.connections:
            self.connections[user_id].discard(ws)
            if not self.connections[user_id]:
                del self.connections[user_id]
        logger.info("WS disconnected | user=%s", user_id)

    # ── 任务绑定 ──

    def bind_task(self, task_id: str, user_id: str, session_id: str):
        """绑定 task_id 到 (user_id, session_id)。"""
        self.task_owners[task_id] = {"user_id": user_id, "session_id": session_id}

    def get_task_owner(self, task_id: str) -> Optional[dict]:
        """查询 task_id 归属，返回 {"user_id": ..., "session_id": ...}。"""
        return self.task_owners.get(task_id)

    def unbind_task(self, task_id: str):
        """解绑任务。"""
        self.task_owners.pop(task_id, None)

    # ── 消息推送 ──

    async def send_to_user(self, user_id: str, message: dict):
        """推送给指定用户的所有连接。

        如果用户离线，缓存消息。
        """
        if user_id not in self.connections:
            # 离线，缓存
            if user_id not in self.offline_cache:
                self.offline_cache[user_id] = []
            self.offline_cache[user_id].append(message)
            logger.info("User offline, cached message | user=%s", user_id)
            return

        # 在线，推送给所有标签页
        dead = []
        for ws in self.connections[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        # 清理断开的连接
        for ws in dead:
            self.connections[user_id].discard(ws)

    # ── 状态查询 ──

    def is_online(self, user_id: str) -> bool:
        return user_id in self.connections and len(self.connections[user_id]) > 0

    def get_stats(self) -> dict:
        return {
            "online_users": len(self.connections),
            "total_connections": sum(len(v) for v in self.connections.values()),
            "pending_tasks": len(self.task_owners),
            "offline_cached": sum(len(v) for v in self.offline_cache.values()),
        }


# 全局单例
ws_manager = WSManager()
