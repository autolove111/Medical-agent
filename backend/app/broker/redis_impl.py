"""
Redis List 消息队列实现

6 个 List 队列，职责清晰：
  medlab:list:task        新任务（API → Loop Worker）
  medlab:list:llm         LLM 请求（Loop Worker → LLM Worker）
  medlab:list:llm_result  LLM 结果（LLM Worker → Loop Worker）
  medlab:list:rag         RAG 请求（Loop Worker → RAG Worker）
  medlab:list:rag_result  RAG 结果（RAG Worker → Loop Worker）
  medlab:list:ocr         OCR 请求（API → OCR Worker）
"""

from __future__ import annotations

import json
import logging
import uuid
import hashlib
from datetime import datetime
from typing import Optional

import redis

from core.config import settings
from broker.interface import MessageBroker

logger = logging.getLogger(__name__)


class RedisBroker(MessageBroker):
    """基于 Redis List 的消息队列实现"""

    # 队列名
    TASK_QUEUE = "medlab:list:task"
    LLM_QUEUE = "medlab:list:llm"
    LLM_RESULT_QUEUE = "medlab:list:llm_result"
    RAG_QUEUE = "medlab:list:rag"
    RAG_RESULT_QUEUE = "medlab:list:rag_result"
    OCR_QUEUE = "medlab:list:ocr"

    # Pub/Sub
    TASK_STREAM_PREFIX = "medlab:task_stream:"

    # 缓存配置
    RAG_CACHE_TTL = 86400
    RAG_CACHE_SIMILARITY = 0.95
    RAG_CACHE_INDEX_KEY = "medlab:rag_cache:index"

    # 任务 TTL: 2 小时（7200 秒）
    TASK_TTL = 7200

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True,
            )
        return self._redis

    def _push(self, queue: str, data: dict) -> None:
        """向队列推送消息。"""
        self.redis.lpush(queue, json.dumps(data, ensure_ascii=False))

    def _pop(self, queue: str, timeout: int = 0) -> Optional[dict]:
        """从队列取消息。timeout=0 非阻塞，timeout>0 阻塞。"""
        if timeout == 0:
            data = self.redis.rpop(queue)
            return json.loads(data) if data else None
        result = self.redis.brpop(queue, timeout=timeout)
        if result is None:
            return None
        _, data = result
        return json.loads(data)

    # ── 主任务 ──

    def submit_task(self, user_id: str, session_id: str, query: str, task_type: str = "chat") -> str:
        task_id = str(uuid.uuid4())
        # 统一用 chat 前缀，task_type 字段存在 Hash 内部区分 ReAct/Plan
        task_key = f"medlab:task:chat:{task_id}"
        now = datetime.now().isoformat()

        self.redis.hset(task_key, "task_id", task_id)
        self.redis.hset(task_key, "user_id", user_id)
        self.redis.hset(task_key, "session_id", session_id)
        self.redis.hset(task_key, "query", query)
        self.redis.hset(task_key, "task_type", task_type)
        self.redis.hset(task_key, "status", "queued")
        self.redis.hset(task_key, "created_at", now)
        self.redis.expire(task_key, self.TASK_TTL)  # 设置 TTL 2小时

        self._push(self.TASK_QUEUE, {
            "task_id": task_id, "user_id": user_id, "session_id": session_id,
            "query": query, "task_type": task_type,
        })

        logger.info("Task submitted | task_id=%s type=%s user=%s", task_id, task_type, user_id)
        return task_id

    def pop_task(self, timeout: int = 0) -> Optional[dict]:
        return self._pop(self.TASK_QUEUE, timeout)

    def update_task_status(self, task_id: str, status: str, task_type: str = "chat", **extra) -> None:
        task_key = f"medlab:task:{task_type}:{task_id}"
        self.redis.hset(task_key, "status", status)
        self.redis.hset(task_key, "updated_at", datetime.now().isoformat())
        for k, v in extra.items():
            val = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            self.redis.hset(task_key, k, val)

    def get_task_status(self, task_id: str, task_type: str = "chat") -> Optional[dict]:
        data = self.redis.hgetall(f"medlab:task:{task_type}:{task_id}")
        return data if data else None

    def expire_task(self, task_id: str, task_type: str = "chat", ttl: int = None) -> None:
        """设置任务 TTL"""
        task_key = f"medlab:task:{task_type}:{task_id}"
        self.redis.expire(task_key, ttl or self.TASK_TTL)

    # ── LLM 请求队列（Loop Worker → LLM Worker）──

    def submit_llm_request(self, task_id: str, messages: list, tools: list = None) -> None:
        self._push(self.LLM_QUEUE, {"task_id": task_id, "messages": messages, "tools": tools or []})
        logger.info("LLM request submitted | task_id=%s", task_id)

    def pop_llm_request(self, timeout: int = 0) -> Optional[dict]:
        return self._pop(self.LLM_QUEUE, timeout)

    # ── LLM 结果队列（LLM Worker → Loop Worker）──

    def push_llm_result(self, message: dict) -> None:
        self._push(self.LLM_RESULT_QUEUE, message)

    def pop_llm_result(self, timeout: int = 0) -> Optional[dict]:
        return self._pop(self.LLM_RESULT_QUEUE, timeout)

    # ── RAG 请求队列（Loop Worker → RAG Worker）──

    def submit_rag_request(self, task_id: str, query: str, top_k: int = 5) -> None:
        self._push(self.RAG_QUEUE, {"task_id": task_id, "query": query, "top_k": top_k})
        logger.info("RAG request submitted | task_id=%s query=%s", task_id, query[:50])

    def pop_rag_request(self, timeout: int = 0) -> Optional[dict]:
        return self._pop(self.RAG_QUEUE, timeout)

    # ── RAG 结果队列（RAG Worker → Loop Worker）──

    def push_rag_result(self, message: dict) -> None:
        self._push(self.RAG_RESULT_QUEUE, message)

    def pop_rag_result(self, timeout: int = 0) -> Optional[dict]:
        return self._pop(self.RAG_RESULT_QUEUE, timeout)

    # ── OCR 请求队列（API → OCR Worker）──

    def submit_ocr_request(self, task_id: str, file_path: str, file_type: str = "image") -> None:
        self._push(self.OCR_QUEUE, {"task_id": task_id, "file_path": file_path, "file_type": file_type})
        logger.info("OCR request submitted | task_id=%s file_type=%s", task_id, file_type)

    def pop_ocr_request(self, timeout: int = 0) -> Optional[dict]:
        return self._pop(self.OCR_QUEUE, timeout)

    # ── 多队列读取 ──

    def pop_any(self, timeout: int = 5) -> tuple[str, Optional[dict]]:
        """轮询 3 个队列，返回 (来源, 数据)。"""
        # 先非阻塞检查所有队列
        for queue, name in [
            (self.TASK_QUEUE, "task"),
            (self.LLM_RESULT_QUEUE, "llm_result"),
            (self.RAG_RESULT_QUEUE, "rag_result"),
        ]:
            data = self._pop(queue, timeout=0)
            if data:
                return (name, data)

        # 都没有，阻塞等待任意一个
        result = self.redis.brpop(
            [self.TASK_QUEUE, self.LLM_RESULT_QUEUE, self.RAG_RESULT_QUEUE],
            timeout=timeout,
        )
        if result is None:
            return ("", None)

        queue_name, data = result
        data = json.loads(data)

        if queue_name == self.TASK_QUEUE:
            return ("task", data)
        elif queue_name == self.LLM_RESULT_QUEUE:
            return ("llm_result", data)
        elif queue_name == self.RAG_RESULT_QUEUE:
            return ("rag_result", data)

        return ("", None)

    # ── Pub/Sub ──

    def publish_stream_chunk(self, task_id: str, chunk_type: str, data: dict) -> None:
        message = json.dumps({"type": chunk_type, "task_id": task_id, **data}, ensure_ascii=False)
        self.redis.publish(f"{self.TASK_STREAM_PREFIX}{task_id}", message)

    # ── RAG 缓存 ──

    def _cache_hash_key(self, query: str, top_k: int = 5) -> str:
        raw = f"{query.strip()}|{top_k}"
        h = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"medlab:rag_cache:{h}"

    def get_rag_cache_exact(self, query: str, top_k: int = 5) -> Optional[list]:
        key = self._cache_hash_key(query, top_k)
        cached = self.redis.hget(key, "results")
        if cached:
            logger.info("RAG cache HIT (exact) | query=%s", query[:50])
            return json.loads(cached)
        return None

    def get_rag_cache_semantic(self, query_embedding: list, top_k: int = 5) -> Optional[list]:
        cache_keys = self.redis.smembers(self.RAG_CACHE_INDEX_KEY)
        if not cache_keys:
            return None

        best_score = 0.0
        best_results = None

        for cache_key in cache_keys:
            data = self.redis.hgetall(cache_key)
            if not data:
                self.redis.srem(self.RAG_CACHE_INDEX_KEY, cache_key)
                continue
            cached_embedding = json.loads(data.get("embedding", "[]"))
            if not cached_embedding:
                continue
            score = self._cosine_similarity(query_embedding, cached_embedding)
            if score > best_score:
                best_score = score
                best_results = json.loads(data.get("results", "[]"))

        if best_score >= self.RAG_CACHE_SIMILARITY and best_results is not None:
            logger.info("RAG cache HIT (semantic) | score=%.3f", best_score)
            return best_results
        return None

    def set_rag_cache(self, query: str, query_embedding: list, results: list, top_k: int = 5) -> None:
        key = self._cache_hash_key(query, top_k)
        self.redis.hset(key, "results", json.dumps(results, ensure_ascii=False))
        self.redis.hset(key, "embedding", json.dumps(query_embedding))
        self.redis.hset(key, "query", query)
        self.redis.expire(key, self.RAG_CACHE_TTL)
        self.redis.sadd(self.RAG_CACHE_INDEX_KEY, key)
        logger.info("RAG cache SET | query=%s results=%d", query[:50], len(results))

    @staticmethod
    def _cosine_similarity(a: list, b: list) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
