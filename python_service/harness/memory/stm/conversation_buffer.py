"""
conversation_buffer.py
~~~~~~~~~~~~~~~~~~~~~~
对话轮次缓冲区：Redis 存储 + 滑动窗口 + 智能压缩。

存储结构（Redis）：
- stm:{session_id}:messages  — List，对话消息队列
- stm:{session_id}:summary   — String，历史摘要（系统消息）
- stm:{session_id}:tokens    — String，当前 token 总数
- stm:{session_id}:meta      — Hash，会话元数据

淘汰策略：滑动窗口 + 历史摘要（推荐）
- 保留最近 K 轮完整对话（默认 5 轮 = 10 条消息）
- 超出部分交给 LLM 生成 200-300 字摘要
- 摘要作为 system 消息插入队列头部
"""

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_MAX_TOKENS = 10000   # 软上限，为 LLM 输入预留空间
DEFAULT_KEEP_ROUNDS = 5      # 保留最近 5 轮（10 条消息）
REDIS_TTL = 86400            # Redis key 过期时间（24 小时）


def _estimate_tokens(text: str) -> int:
    """估算 token 数量（CJK 1.5 token/字，其他 0.25 token/字符）"""
    cjk_count = sum(1 for ch in text if "一" <= ch <= "鿿")
    other_count = len(text) - cjk_count
    return int(cjk_count * 1.5 + other_count * 0.25)


class ConversationBuffer:
    """
    对话轮次缓冲区（Redis 持久化）

    使用方式：
        buffer = ConversationBuffer(session_id="s001", redis_client=redis)
        buffer.add("user", "我头晕")
        buffer.add("assistant", "可能是因为...")
        recent = buffer.get_recent(n=5)
    """

    def __init__(
        self,
        session_id: str,
        redis_client,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        keep_rounds: int = DEFAULT_KEEP_ROUNDS,
    ):
        self.session_id = session_id
        self._redis = redis_client
        self.max_tokens = max_tokens
        self.keep_rounds = keep_rounds

        # Redis key 前缀
        self._key_msgs = f"stm:{session_id}:messages"
        self._key_summary = f"stm:{session_id}:summary"
        self._key_tokens = f"stm:{session_id}:tokens"
        self._key_meta = f"stm:{session_id}:meta"

        # 内存缓存（从 Redis 加载）
        self._messages: List[Dict] = []
        self._summary: str = ""
        self._total_tokens: int = 0
        self._loaded = False

    # ---- 属性 ----

    @property
    def total_tokens(self) -> int:
        if not self._loaded:
            self._load_from_redis()
        return self._total_tokens

    @property
    def messages(self) -> List[Dict]:
        if not self._loaded:
            self._load_from_redis()
        return self._messages

    @property
    def summary(self) -> str:
        if not self._loaded:
            self._load_from_redis()
        return self._summary

    # ---- 核心操作 ----

    def add(self, role: str, content: str) -> None:
        """添加一条消息到缓冲区"""
        if not self._loaded:
            self._load_from_redis()

        tokens = _estimate_tokens(content)
        msg = {
            "role": role,
            "content": content,
            "tokens": tokens,
        }
        self._messages.append(msg)
        self._total_tokens += tokens

        # 持久化到 Redis（如果有连接）
        if self._redis:
            try:
                self._redis.rpush(self._key_msgs, json.dumps(msg, ensure_ascii=False))
                self._redis.set(self._key_tokens, str(self._total_tokens))
                self._redis.expire(self._key_msgs, REDIS_TTL)
                self._redis.expire(self._key_tokens, REDIS_TTL)
            except Exception as e:
                logger.warning("Redis write failed: %s", e)

        logger.debug(
            "Buffer add: role=%s, tokens=%d, total=%d/%d",
            role, tokens, self._total_tokens, self.max_tokens,
        )

    def get_recent(self, n: int) -> List[Dict]:
        """获取最近 n 轮对话（摘要 + 最近消息）"""
        if not self._loaded:
            self._load_from_redis()

        result = []
        if self._summary:
            result.append({
                "role": "system",
                "content": self._summary,
                "tokens": _estimate_tokens(self._summary),
                "type": "summary",
            })

        # n 轮 = 2n 条消息
        recent_count = n * 2
        recent_msgs = self._messages[-recent_count:] if recent_count > 0 else self._messages
        result.extend(recent_msgs)
        return result

    def get_all(self) -> List[Dict]:
        """获取所有内容（摘要 + 全部消息）"""
        if not self._loaded:
            self._load_from_redis()

        result = []
        if self._summary:
            result.append({
                "role": "system",
                "content": self._summary,
                "tokens": _estimate_tokens(self._summary),
                "type": "summary",
            })
        result.extend(self._messages)
        return result

    def get_oldest(self, n: int) -> List[Dict]:
        """获取最早的 n 条消息（用于压缩）"""
        if not self._loaded:
            self._load_from_redis()
        return self._messages[:n]

    def needs_compression(self) -> bool:
        """检查是否需要压缩"""
        if not self._loaded:
            self._load_from_redis()
        return self._total_tokens > self.max_tokens

    def get_compress_count(self) -> int:
        """计算需要压缩的消息数量：保留最近 keep_rounds 轮，压缩其余"""
        if not self._loaded:
            self._load_from_redis()

        keep_count = self.keep_rounds * 2  # 轮次 → 消息数
        total = len(self._messages)
        if total <= keep_count:
            return 0  # 不需要压缩
        return total - keep_count

    def replace_with_summary(self, summary_text: str, removed_count: int) -> None:
        """
        用摘要替换最早的消息

        流程：
        1. 移除最早的 removed_count 条消息
        2. 设置新的摘要
        3. 重新计算 token 数
        4. 同步到 Redis
        """
        if not self._loaded:
            self._load_from_redis()

        # 计算被移除消息的 token 数
        removed_msgs = self._messages[:removed_count]
        removed_tokens = sum(m.get("tokens", 0) for m in removed_msgs)

        # 移除消息
        self._messages = self._messages[removed_count:]

        # 设置摘要
        self._summary = summary_text
        summary_tokens = _estimate_tokens(summary_text)

        # 重新计算 token
        self._total_tokens = self._total_tokens - removed_tokens + summary_tokens

        # 同步到 Redis
        self._sync_to_redis()

        logger.info(
            "Compressed %d messages (%d tokens) → summary (%d tokens), total now %d",
            removed_count, removed_tokens, summary_tokens, self._total_tokens,
        )

    def clear(self) -> None:
        """清空缓冲区"""
        self._messages = []
        self._summary = ""
        self._total_tokens = 0

        if self._redis:
            try:
                self._redis.delete(self._key_msgs, self._key_summary, self._key_tokens, self._key_meta)
            except Exception:
                pass

        logger.debug("Buffer cleared: %s", self.session_id)

    # ---- Redis 操作 ----

    def _load_from_redis(self) -> None:
        """从 Redis 加载数据到内存"""
        self._loaded = True

        if not self._redis:
            return

        try:
            # 加载消息列表
            raw_msgs = self._redis.lrange(self._key_msgs, 0, -1)
            self._messages = [json.loads(m) for m in raw_msgs] if raw_msgs else []

            # 加载摘要
            raw_summary = self._redis.get(self._key_summary)
            self._summary = raw_summary.decode() if isinstance(raw_summary, bytes) else (raw_summary or "")

            # 加载 token 数
            raw_tokens = self._redis.get(self._key_tokens)
            if raw_tokens:
                self._total_tokens = int(raw_tokens.decode() if isinstance(raw_tokens, bytes) else raw_tokens)
            else:
                # 重新计算
                self._total_tokens = sum(m.get("tokens", 0) for m in self._messages)
                if self._summary:
                    self._total_tokens += _estimate_tokens(self._summary)

            logger.debug(
                "Loaded from Redis: %d messages, summary=%d chars, tokens=%d",
                len(self._messages), len(self._summary), self._total_tokens,
            )
        except Exception as e:
            logger.error("Failed to load from Redis: %s", e)
            self._messages = []
            self._summary = ""
            self._total_tokens = 0

    def _sync_to_redis(self) -> None:
        """将当前状态完整同步到 Redis"""
        if not self._redis:
            return

        try:
            pipe = self._redis.pipeline()

            # 清空旧数据
            pipe.delete(self._key_msgs)

            # 写入消息列表
            if self._messages:
                pipe.rpush(
                    self._key_msgs,
                    *[json.dumps(m, ensure_ascii=False) for m in self._messages]
                )

            # 写入摘要
            if self._summary:
                pipe.set(self._key_summary, self._summary)
            else:
                pipe.delete(self._key_summary)

            # 写入 token 数
            pipe.set(self._key_tokens, str(self._total_tokens))

            # 设置过期
            pipe.expire(self._key_msgs, REDIS_TTL)
            pipe.expire(self._key_summary, REDIS_TTL)
            pipe.expire(self._key_tokens, REDIS_TTL)

            pipe.execute()
            logger.debug("Synced to Redis: %d messages, tokens=%d", len(self._messages), self._total_tokens)
        except Exception as e:
            logger.error("Failed to sync to Redis: %s", e)
