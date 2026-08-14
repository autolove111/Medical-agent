"""
Redis Broker 兼容层

保留原有函数式 API，底层委托给 RedisBroker 实例（基于 Streams）。
"""

from broker.redis_impl import RedisBroker

# 全局单例
_broker = RedisBroker()

# 常量（向后兼容）
TASK_RESULT_CHANNEL = "medlab:task_result"
TASK_STREAM_PREFIX = RedisBroker.TASK_STREAM_PREFIX


def submit_task(user_id: str, session_id: str, query: str, task_type: str = "chat") -> str:
    return _broker.submit_task(user_id, session_id, query, task_type)


def pop_task(timeout: int = 0):
    return _broker.pop_task(timeout)


def update_task_status(task_id: str, status: str, task_type: str = "chat", **extra):
    return _broker.update_task_status(task_id, status, task_type=task_type, **extra)


def get_task_status(task_id: str, task_type: str = "chat"):
    return _broker.get_task_status(task_id, task_type=task_type)


def expire_task(task_id: str, task_type: str = "chat", ttl: int = None):
    return _broker.expire_task(task_id, task_type=task_type, ttl=ttl)


def submit_llm_request(task_id: str, messages: list, tools: list = None):
    return _broker.submit_llm_request(task_id, messages, tools)


def pop_llm_request(timeout: int = 0):
    return _broker.pop_llm_request(timeout)


def submit_rag_request(task_id: str, query: str, top_k: int = 5):
    return _broker.submit_rag_request(task_id, query, top_k)


def pop_rag_request(timeout: int = 0):
    return _broker.pop_rag_request(timeout)


def push_llm_result(message: dict):
    return _broker.push_llm_result(message)


def pop_llm_result(timeout: int = 0):
    return _broker.pop_llm_result(timeout)


def push_rag_result(message: dict):
    return _broker.push_rag_result(message)


def pop_rag_result(timeout: int = 0):
    return _broker.pop_rag_result(timeout)


def submit_ocr_request(task_id: str, file_path: str, file_type: str = "image"):
    return _broker.submit_ocr_request(task_id, file_path, file_type)


def pop_ocr_request(timeout: int = 0):
    return _broker.pop_ocr_request(timeout)


def publish_stream_chunk(task_id: str, chunk_type: str, data: dict):
    return _broker.publish_stream_chunk(task_id, chunk_type, data)


def publish_result(task_id: str, status: str, result: str = "", error: str = ""):
    return _broker.publish_stream_chunk(task_id, "task_result", {
        "status": status, "result": result, "error": error,
    })


def subscribe_result():
    import redis as _redis
    from core.config import settings as _settings
    r = _redis.Redis(
        host=_settings.REDIS_HOST, port=_settings.REDIS_PORT,
        password=_settings.REDIS_PASSWORD or None, decode_responses=True,
    )
    pubsub = r.pubsub()
    pubsub.subscribe("medlab:task_result")
    return pubsub


def get_rag_cache_exact(query: str, top_k: int = 5):
    return _broker.get_rag_cache_exact(query, top_k)


def get_rag_cache_semantic(query_embedding: list, top_k: int = 5):
    return _broker.get_rag_cache_semantic(query_embedding, top_k)


def set_rag_cache(query: str, query_embedding: list, results: list, top_k: int = 5):
    return _broker.set_rag_cache(query, query_embedding, results, top_k)
