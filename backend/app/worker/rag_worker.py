"""
RAG Worker：从 RAG 队列拉取检索请求，执行检索，返回结果

启动方式：
    cd backend
    python -m app.worker.rag_worker
"""

import logging
import sys
import os
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RAG-Worker] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rag_worker")

# 路径设置
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DIR = os.path.dirname(_APP_DIR)
_AI_DIR = os.path.join(_PROJECT_DIR, "..", "ai-services")

for _p in [_APP_DIR, _AI_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _get_embedding(query: str) -> list:
    from rag.config import create_embed_model
    embed_model = create_embed_model()
    return embed_model.get_text_embedding(query)


def do_rag_search(query: str, top_k: int = 5, broker=None) -> list:
    """执行 RAG 检索。"""
    # 查缓存
    if broker:
        cached = broker.get_rag_cache_exact(query, top_k)
        if cached is not None:
            return cached
        query_embedding = _get_embedding(query)
        cached = broker.get_rag_cache_semantic(query_embedding, top_k)
        if cached is not None:
            return cached
    else:
        query_embedding = _get_embedding(query)

    # 完整 RAG 流程
    from rag.config import init_llama_settings
    init_llama_settings()

    from rag.retrieval.retrievers import create_hybrid_retriever
    from rag.retrieval.rerankers import get_reranker
    from rag.ingestion.index_builder import load_index
    from llama_index.core.schema import QueryBundle, TextNode
    from core.config import settings
    import psycopg2

    index = load_index()
    if index is None:
        logger.error("RAG index not found")
        return []

    conn = psycopg2.connect(
        host="localhost", port=5432,
        database="medlab_db",
        user="medlab_user", password="medlab_password",
    )
    cur = conn.cursor()
    cur.execute("SELECT node_id, text, metadata_ FROM data_knowledge_vectors")
    rows = cur.fetchall()
    conn.close()
    nodes = [TextNode(id_=nid, text=txt, metadata=meta or {}) for nid, txt, meta in rows]

    recall_k = settings.RERANKER_TOP_K if settings.RERANKER_ENABLED else top_k
    hybrid_ret = create_hybrid_retriever(index, nodes, similarity_top_k=recall_k)
    candidates = hybrid_ret.retrieve(QueryBundle(query_str=query))

    reranker = get_reranker()
    if reranker.is_available:
        ranked = reranker.rerank(query, candidates, top_k=top_k)
    else:
        ranked = candidates[:top_k]

    results = []
    for node in ranked:
        results.append({
            "content": node.get_content(),
            "score": float(node.score) if node.score else 0.0,
            "metadata": node.metadata or {},
        })

    if broker:
        broker.set_rag_cache(query, query_embedding, results, top_k)

    return results


def main():
    from broker.redis_impl import RedisBroker

    broker = RedisBroker()

    logger.info("=" * 50)
    logger.info("RAG Worker started")
    logger.info("=" * 50)

    try:
        from rag.config import init_llama_settings
        init_llama_settings()
        logger.info("RAG warmup complete")
    except Exception as exc:
        logger.warning("RAG warmup failed: %s", exc)

    while True:
        try:
            request = broker.pop_rag_request(timeout=5)
            if request is None:
                continue

            task_id = request["task_id"]
            query = request["query"]
            top_k = request.get("top_k", 5)

            logger.info("▶ RAG request | task_id=%s query=%s", task_id, query[:50])

            start = time.time()
            results = do_rag_search(query, top_k, broker=broker)
            elapsed = time.time() - start

            broker.push_rag_result({
                "type": "rag_result",
                "task_id": task_id,
                "results": results,
            })
            logger.info("✓ RAG done | task_id=%s results=%d elapsed=%.1fs", task_id, len(results), elapsed)

        except KeyboardInterrupt:
            logger.info("RAG Worker interrupted")
            break
        except Exception as exc:
            logger.error("RAG Worker error: %s", exc, exc_info=True)
            if "task_id" in locals():
                broker.push_rag_result({
                    "type": "rag_result",
                    "task_id": task_id,
                    "results": [],
                    "error": str(exc),
                })


if __name__ == "__main__":
    main()
