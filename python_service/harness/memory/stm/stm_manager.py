"""
stm_manager.py
~~~~~~~~~~~~~~
短期记忆统一管理器（Redis 持久化 + 滑动窗口压缩）。

架构：
- 存储层：Redis（消息列表、摘要、token 计数）
- 压缩层：滑动窗口 + LLM 摘要（保留最近 5 轮，早期压缩为 200-300 字摘要）
- 状态层：StateTracker（问诊阶段追踪）

压缩触发条件：
- 每次 add_message 后检查 token 总数
- 超过软上限（10K tokens）时触发压缩
- 压缩策略：保留最近 5 轮（10 条消息），更早的消息交给 LLM 生成摘要
"""

import json
import logging
import time
from typing import Callable, Dict, List, Optional

import redis as redis_lib

from .conversation_buffer import ConversationBuffer, DEFAULT_MAX_TOKENS, DEFAULT_KEEP_ROUNDS
from .compressor import ConversationCompressor
from .state_tracker_engine import StateTrackerEngine
from ..models.state_tracker import StateTracker
from ..models.user_profile import UserProfile
from ..models.conversation_message import ConversationMessage

logger = logging.getLogger(__name__)

# 全局注册表
_active_instances: Dict[str, "STMManager"] = {}


def get_active_stm(user_id: str) -> Optional["STMManager"]:
    """获取某用户的活跃 STM 实例"""
    return _active_instances.get(user_id)


def list_active_stms() -> Dict[str, "STMManager"]:
    """列出所有活跃的 STM 实例"""
    return dict(_active_instances)


def _create_redis_client(host: str = "localhost", port: int = 6379, password: str = "") -> Optional[redis_lib.Redis]:
    """创建 Redis 客户端"""
    try:
        client = redis_lib.Redis(
            host=host,
            port=port,
            password=password if password else None,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        client.ping()
        logger.info("Redis connected: %s:%s", host, port)
        return client
    except Exception as e:
        logger.warning("Redis unavailable: %s", e)
        return None


class STMManager:
    """
    短期记忆统一管理器

    使用方式：
        stm = STMManager(session_id="s001", user_id="u001", redis_client=redis)
        stm.add_message("user", "我头晕")
        stm.add_message("assistant", "可能是因为...")
        recent = stm.get_recent_messages(n=5)
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        redis_client=None,
        llm_caller: Optional[Callable[[str], str]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        keep_rounds: int = DEFAULT_KEEP_ROUNDS,
        ltm_manager=None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self._ltm = ltm_manager  # 长期记忆管理器，压缩时写入

        # Redis 客户端
        self._redis = redis_client
        if self._redis is None:
            # 尝试从配置创建
            try:
                from core.config import settings
                self._redis = _create_redis_client(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    password=settings.REDIS_PASSWORD,
                )
            except Exception:
                self._redis = None

        # 对话缓冲区（Redis 持久化）
        self.conversation_buffer = ConversationBuffer(
            session_id=session_id,
            redis_client=self._redis,
            max_tokens=max_tokens,
            keep_rounds=keep_rounds,
        )

        # 压缩器
        self.compressor = ConversationCompressor(llm_caller)

        # 状态追踪
        self.state_tracker = StateTracker(session_id=session_id)
        self.state_engine = StateTrackerEngine(llm_caller)

        # 用户画像（从 LTM 加载）
        self.user_profile: Optional[UserProfile] = None

        # 注册到全局表
        _active_instances[user_id] = self

        logger.info(
            "STMManager initialized: session=%s, user=%s, max_tokens=%d, keep_rounds=%d, redis=%s",
            session_id, user_id, max_tokens, keep_rounds,
            "connected" if self._redis else "disabled",
        )

    # ---- 对话缓冲区 ----

    def add_message(self, role: str, content: str) -> None:
        """
        添加对话消息

        流程：
        1. 写入 Redis 缓冲区
        2. 检查 token 是否超过软上限
        3. 如果超过，触发滑动窗口压缩
        """
        self.conversation_buffer.add(role, content)

        if self.conversation_buffer.needs_compression():
            self._compress_sliding_window()

        logger.debug(
            "Added message: role=%s, tokens=%d/%d",
            role,
            self.conversation_buffer.total_tokens,
            self.conversation_buffer.max_tokens,
        )

    def get_recent_messages(self, n: int = 5) -> List[Dict]:
        """获取最近 n 轮对话（含摘要）"""
        return self.conversation_buffer.get_recent(n)

    def get_all_messages(self) -> List[Dict]:
        """获取所有消息（含摘要）"""
        return self.conversation_buffer.get_all()

    # ---- 状态追踪 ----

    def update_state(self, state_update: Dict) -> None:
        self.state_tracker.apply_update(state_update)

    def get_state_text(self) -> str:
        return self.state_tracker.to_prompt_text()

    # ---- 持久化 ----

    def save_to_redis(self) -> bool:
        """手动保存到 Redis（通常不需要，add_message 已自动持久化）"""
        if not self._redis:
            return False
        try:
            state_key = f"stm:{self.session_id}:state"
            self._redis.setex(state_key, 86400, json.dumps(self.state_tracker.to_dict()))
            return True
        except Exception as e:
            logger.error("Failed to save state to Redis: %s", e)
            return False

    def load_from_redis(self) -> bool:
        """从 Redis 恢复（消息已在 ConversationBuffer 中自动加载）"""
        if not self._redis:
            return False
        try:
            state_key = f"stm:{self.session_id}:state"
            raw = self._redis.get(state_key)
            if raw:
                self.state_tracker = StateTracker.from_dict(json.loads(raw))
            return True
        except Exception as e:
            logger.error("Failed to load state from Redis: %s", e)
            return False

    def clear(self) -> None:
        """清空所有记忆"""
        self.conversation_buffer.clear()
        self.state_tracker = StateTracker(session_id=self.session_id)

        if self._redis:
            try:
                state_key = f"stm:{self.session_id}:state"
                self._redis.delete(state_key)
            except Exception:
                pass

        logger.debug("STM cleared: %s", self.session_id)

    # ---- 内部方法 ----

    def _compress_sliding_window(self) -> None:
        """
        滑动窗口压缩 + LTM 归档

        策略：
        1. 计算需要压缩的消息数（总消息 - 保留轮次 * 2）
        2. 取出最早的消息
        3. 将被压缩的消息写入 LTM（持久化到 session_data 表）
        4. 交给 LLM 生成摘要
        5. 用摘要替换 STM 中的原消息
        """
        compress_count = self.conversation_buffer.get_compress_count()
        if compress_count <= 0:
            return

        # 取出待压缩的消息
        oldest = self.conversation_buffer.get_oldest(compress_count)
        if not oldest:
            return

        logger.info(
            "Compressing %d messages (keeping last %d rounds)",
            compress_count, self.conversation_buffer.keep_rounds,
        )

        # ★ 将被压缩的消息写入 LTM（归档）
        self._archive_to_ltm(oldest)

        # 生成摘要
        summary = self.compressor.compress(oldest, max_chars=600)

        if summary:
            # 用摘要替换原消息
            self.conversation_buffer.replace_with_summary(summary, compress_count)
            logger.info(
                "Compression done: %d messages → summary (%d chars), tokens now %d",
                compress_count, len(summary), self.conversation_buffer.total_tokens,
            )
        else:
            logger.warning("Compression produced empty summary, keeping messages as-is")

    def _archive_to_ltm(self, messages: List[Dict]) -> None:
        """
        将消息写入长期记忆（session_data 表）

        压缩时调用，确保对话原文不会因压缩而丢失。
        """
        if not self._ltm:
            logger.debug("No LTM manager, skipping archive")
            return

        try:
            conversation_messages = []
            for i, msg in enumerate(messages):
                role = msg.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                conversation_messages.append(
                    ConversationMessage(
                        user_id=self.user_id,
                        session_id=self.session_id,
                        turn_number=i // 2 + 1,
                        role=role,
                        content=msg.get("content", ""),
                    )
                )

            if conversation_messages:
                self._ltm.save_conversation(self.session_id, conversation_messages)
                logger.info(
                    "Archived %d messages to LTM (session=%s)",
                    len(conversation_messages), self.session_id,
                )
        except Exception as e:
            logger.error("Failed to archive to LTM: %s", e)
