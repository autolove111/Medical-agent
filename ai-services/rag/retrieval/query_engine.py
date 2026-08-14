"""
查询引擎 — RAG 检索流水线统一入口

组装：混合检索 → 重排序 → 结果格式化

对外暴露 retrieve(query) 接口，兼容原有 rag.py 的调用方式。
"""

import logging
import threading
from typing import List, Optional, Tuple

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import BaseNode, NodeWithScore

from core.config import settings
from rag.config import init_llama_settings, create_reranker, LLAMA_INDEX_DB_DIR
from rag.ingestion.index_builder import load_index, build_index
from rag.retrieval.retrievers import (
    create_vector_retriever,
    create_bm25_retriever,
    create_hybrid_retriever,
)
from rag.retrieval.rerankers import get_reranker, CrossEncoderReranker
from rag.retrieval.response_synthesizer import (
    format_nodes_as_answer,
    extract_source_metadata,
)

logger = logging.getLogger(__name__)


def _preview_text(text: str, limit: int = 200) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= limit else compact[:limit] + "..."


class QueryEngine:
    """RAG 查询引擎（单例模式，线程安全）。

    使用方式：
        engine = QueryEngine()
        answer, docs = engine.retrieve("肌酐偏高怎么办")
    """

    def __init__(self, use_es: bool = True):
        self._index: Optional[VectorStoreIndex] = None
        self._nodes: Optional[List[BaseNode]] = None  # 供 BM25 使用
        self._reranker: Optional[CrossEncoderReranker] = None
        self._hybrid_retriever = None  # 缓存混合检索器（避免重复建 BM25 索引）
        self._initialized = False
        self._init_error: Optional[Exception] = None
        self._use_es = use_es  # 是否使用 ES 做 BM25

    def _ensure_initialized(self) -> bool:
        """确保索引和检索组件已初始化。"""
        if self._initialized:
            return True

        try:
            logger.info("Initializing QueryEngine...")

            # 初始化 LlamaIndex 全局设置
            init_llama_settings()

            # 加载索引
            self._index = load_index()
            if self._index is None:
                logger.warning("No persisted index found, building from source...")
                self._index = build_index()

            # 提取所有 node（供 BM25 检索器使用）
            # 从 PostgreSQL 加载，用 SQL 直接查
            import psycopg2
            from llama_index.core.schema import TextNode
            conn = psycopg2.connect(
                host="localhost", port=5432,
                database="medlab_db",
                user="medlab_user", password="medlab_password"
            )
            cur = conn.cursor()
            cur.execute("SELECT node_id, text, metadata_ FROM data_knowledge_vectors")
            rows = cur.fetchall()
            conn.close()
            self._nodes = []
            for node_id, text, metadata in rows:
                node = TextNode(id_=node_id, text=text, metadata=metadata or {})
                self._nodes.append(node)
            logger.info("Loaded %d nodes from PostgreSQL for BM25", len(self._nodes))

            # 初始化重排序器
            self._reranker = get_reranker()

            self._initialized = True
            logger.info(
                "QueryEngine initialized | nodes=%d reranker=%s",
                len(self._nodes),
                "available" if self._reranker and self._reranker.is_available else "disabled",
            )
            return True

        except Exception as exc:
            self._init_error = exc
            logger.error("QueryEngine init failed: %s", exc, exc_info=True)
            return False

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        use_hybrid: bool = True,
        use_rerank: bool = True,
    ) -> Tuple[str, List]:
        """执行 RAG 检索。

        Args:
            query: 用户查询（直接作为检索向量，不做改写）
            top_k: 返回的文档数
            use_hybrid: 是否使用混合检索（向量 + BM25）
            use_rerank: 是否使用重排序

        Returns:
            (answer_text, nodes)：格式化文本 + NodeWithScore 列表
        """
        normalized_query = (query or "").strip()
        if not normalized_query:
            return "", []

        if not self._ensure_initialized():
            logger.error("QueryEngine not ready, skipping retrieval")
            return "", []

        try:
            from llama_index.core.schema import QueryBundle
            query_bundle = QueryBundle(query_str=normalized_query)
            final_top_k = top_k or settings.RAG_TOP_K
            recall_top_k = settings.RERANKER_TOP_K if use_rerank else final_top_k

            # ── 阶段1: BM25 关键词检索 ──
            bm25_retriever = create_bm25_retriever(
                self._nodes, similarity_top_k=recall_top_k, use_es=self._use_es)
            bm25_nodes = bm25_retriever.retrieve(query_bundle)
            retrieval_log.info(
                "[BM25] query=\"%s\" results=%d top3=%s",
                normalized_query[:50], len(bm25_nodes),
                [(n.node.node_id, round(n.score or 0, 4)) for n in bm25_nodes[:3]]
            )

            # ── 阶段2: 向量语义检索 ──
            vec_retriever = create_vector_retriever(self._index, recall_top_k)
            vec_nodes = vec_retriever.retrieve(query_bundle)
            retrieval_log.info(
                "[向量] query=\"%s\" results=%d top3=%s",
                normalized_query[:50], len(vec_nodes),
                [(n.node.node_id, round(n.score or 0, 4)) for n in vec_nodes[:3]]
            )

            # ── 阶段3: 混合检索 RRF ──
            if use_hybrid:
                if self._hybrid_retriever is None:
                    self._hybrid_retriever = create_hybrid_retriever(
                        self._index, self._nodes,
                        similarity_top_k=recall_top_k,
                        use_es=self._use_es,
                    )
                rrf_nodes = self._hybrid_retriever.retrieve(query_bundle)
            else:
                rrf_nodes = vec_nodes
            retrieval_log.info(
                "[混合RRF] query=\"%s\" results=%d top3=%s",
                normalized_query[:50], len(rrf_nodes),
                [(n.node.node_id, round(n.score or 0, 4)) for n in rrf_nodes[:3]]
            )

            # ── 阶段4: 重排序 ──
            nodes = rrf_nodes
            if use_rerank and self._reranker and self._reranker.is_available:
                nodes = self._reranker.rerank(
                    normalized_query,
                    rrf_nodes,
                    top_k=top_k or settings.RERANKER_FINAL_K,
                )
            retrieval_log.info(
                "[重排序] query=\"%s\" results=%d top3=%s",
                normalized_query[:50], len(nodes),
                [(n.node.node_id, round(n.score or 0, 4)) for n in nodes[:3]]
            )

            # ── 汇总日志 ──
            retrieval_log.info(
                "查询完成 | BM25=%d 向量=%d RRF=%d 重排=%d | query=%s",
                len(bm25_nodes), len(vec_nodes), len(rrf_nodes), len(nodes),
                normalized_query[:50],
            )

            # 格式化输出
            answer = format_nodes_as_answer(nodes)

            logger.info(
                "RAG result | nodes=%d answer_preview=%s",
                len(nodes),
                _preview_text(answer, 300),
            )

            return answer, nodes

        except Exception as exc:
            logger.error("RAG retrieval failed: %s", exc, exc_info=True)
            return "", []


# ============================================================
# 全局单例
# ============================================================

_query_engine: Optional[QueryEngine] = None
_query_engine_lock = threading.Lock()


def get_query_engine(use_es: bool = True) -> QueryEngine:
    """获取全局 QueryEngine 单例。

    Args:
        use_es: 是否使用 Elasticsearch 做 BM25 检索（默认 False）
    """
    global _query_engine
    if _query_engine is not None:
        return _query_engine

    with _query_engine_lock:
        if _query_engine is None:
            _query_engine = QueryEngine(use_es=use_es)
    return _query_engine


def retrieve(
    query: str,
    **kwargs,
) -> Tuple[str, List]:
    """便捷检索函数（兼容原有 retrieve_medical_knowledge 接口）。"""
    return get_query_engine().retrieve(query, **kwargs)
