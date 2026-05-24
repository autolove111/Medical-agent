import json
import logging
from typing import List, Optional, Tuple

import redis
from langchain_core.documents import Document

from core.config import settings
from knowledge.rag_formatter import deserialize_documents, serialize_documents

logger = logging.getLogger(__name__)


def create_redis_client() -> Optional[redis.Redis]:
    try:
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        client.ping()
        logger.info("Redis cache ready (%s:%s)", settings.REDIS_HOST, settings.REDIS_PORT)
        return client
    except Exception as exc:
        logger.warning("Redis unavailable, cache disabled: %s", exc)
        return None


class RAGCache:
    def __init__(self, client: Optional[redis.Redis] = None, ttl_seconds: Optional[int] = None):
        self.client = client if client is not None else create_redis_client()
        self.ttl_seconds = ttl_seconds or getattr(settings, "RAG_CACHE_TTL_SECONDS", 86400)

    def get(self, cache_key: str) -> Optional[Tuple[str, List[Document]]]:
        if self.client is None:
            return None

        cached = self.client.get(cache_key)
        if not cached:
            return None

        data = json.loads(cached)
        return data.get("answer", ""), deserialize_documents(data.get("sources", []))

    def set(self, cache_key: str, answer: str, documents: List[Document]) -> None:
        if self.client is None:
            return

        payload = json.dumps(
            {
                "answer": answer,
                "sources": serialize_documents(documents),
            },
            ensure_ascii=False,
        )
        self.client.setex(cache_key, self.ttl_seconds, payload)
