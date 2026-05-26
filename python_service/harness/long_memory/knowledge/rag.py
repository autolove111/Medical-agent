import logging
import threading
from typing import Optional, Tuple

from knowledge.embedding_FAISS import create_embeddings
from knowledge.hybrid_retriever import HybridRetriever
from knowledge.rag_cache import RAGCache
from knowledge.rag_formatter import format_documents_as_answer
from knowledge.rag_retriever import GlobalRetrieverRegistry

logger = logging.getLogger(__name__)


def _preview_text(text: str, limit: int = 300) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


class RAGSystem:
    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self.rag_chain = None
        self.hybrid_retriever: Optional[HybridRetriever] = None
        self.redis_client = None
        self.cache = None
        self.retriever_registry = None
        self.last_init_error = None
        self._initialize()

    def _initialize(self) -> None:
        try:
            self.embeddings = None
            self.vectorstore = None
            self.rag_chain = None
            self.hybrid_retriever = None
            self.redis_client = None
            self.cache = None
            self.retriever_registry = None
            self.last_init_error = None

            logger.info("=" * 40)
            logger.info("Starting RAG system initialization")

            self.embeddings = create_embeddings(purpose="rag")
            logger.info("RAG initialized with local embedding model")

            self.cache = RAGCache()
            self.redis_client = self.cache.client
            self.retriever_registry = GlobalRetrieverRegistry(self.embeddings)

            # 构建混合检索引擎（关键词 + 语义 + 重排序）
            faiss_retriever = self.retriever_registry.get_retriever()
            if faiss_retriever is not None:
                self.hybrid_retriever = HybridRetriever(faiss_retriever)
                logger.info("Hybrid retriever initialized (keyword + semantic + rerank)")
            else:
                logger.warning("FAISS retriever not available, hybrid search disabled")

            logger.info("RAG components initialized")
            logger.info("=" * 40)
        except Exception as exc:
            self.last_init_error = exc
            logger.error("RAG initialization failed: %s", exc, exc_info=True)

    def _get_faiss_retriever(self):
        """延迟获取 FAISS retriever（向量库可能尚未加载）"""
        if self.hybrid_retriever is not None:
            return self.hybrid_retriever.faiss_retriever

        if self.retriever_registry is None:
            return None
        faiss_retriever = self.retriever_registry.get_retriever()
        if faiss_retriever is not None and self.hybrid_retriever is None:
            self.hybrid_retriever = HybridRetriever(faiss_retriever)
            self.vectorstore = self.retriever_registry.vectorstore
        return faiss_retriever

    def _is_ready(self) -> bool:
        return self.retriever_registry is not None and self.cache is not None

    def _ensure_ready(self) -> bool:
        if self._is_ready():
            return True

        logger.warning(
            "RAG system is not ready, retrying initialization | last_error=%s",
            self.last_init_error,
        )
        self._initialize()
        return self._is_ready()

    def retrieve(
        self,
        query: str,
    ) -> Tuple[str, list]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return "", []

        if not self._ensure_ready():
            logger.error("RAG system is not ready after retry, skipping retrieval")
            return "", []

        faiss_retriever = self._get_faiss_retriever()
        if faiss_retriever is None:
            logger.error("No retriever available for global vectorstore")
            return "", []

        try:
            # 缓存检查（使用原始查询作为 key，保证缓存精确性）
            cached = self.cache.get(normalized_query)
            if cached is not None:
                cached_answer, cached_docs = cached
                logger.info(
                    "RAG cache hit | docs=%d query=%s preview=%s",
                    len(cached_docs or []),
                    normalized_query[:200],
                    _preview_text(cached_answer, 200),
                )
                return cached

            # 混合检索：关键词 + 语义 + 重排序 + 截断
            if self.hybrid_retriever is not None:
                docs, meta = self.hybrid_retriever.hybrid_search(
                    normalized_query,
                    top_k=5,
                    use_query_rewrite=True,
                )
                logger.info(
                    "Hybrid search | rewrite='%s' | ref=%d faiss=%d -> ranked=%d",
                    str(meta.get("query_rewritten", ""))[:80],
                    meta.get("ref_docs", 0),
                    meta.get("faiss_docs", 0),
                    len(docs),
                )
            else:
                # 回退纯语义检索
                docs = list(faiss_retriever.invoke(normalized_query))

            logger.info(
                "RAG retrieved docs | count=%d query=%s",
                len(docs),
                normalized_query[:200],
            )
            for index, doc in enumerate(docs, start=1):
                metadata = getattr(doc, "metadata", {}) or {}
                source = metadata.get("source", "unknown")
                logger.info(
                    "RAG doc %d | source=%s | preview=%s",
                    index,
                    source,
                    _preview_text(getattr(doc, "page_content", ""), 300),
                )
            answer = format_documents_as_answer(docs)
            logger.info(
                "RAG formatted answer | preview=%s",
                _preview_text(answer, 500),
            )
            self.cache.set(normalized_query, answer, docs)
            return answer, docs
        except Exception as exc:
            logger.error("RAG retrieval failed: %s", exc, exc_info=True)
            return "", []


_rag_system: Optional[RAGSystem] = None
_rag_system_lock = threading.Lock()


def get_rag_system() -> RAGSystem:
    global _rag_system
    if _rag_system is not None:
        return _rag_system

    with _rag_system_lock:
        if _rag_system is None:
            _rag_system = RAGSystem()
    return _rag_system


def retrieve_medical_knowledge(
    query: str,
) -> Tuple[str, list]:
    return get_rag_system().retrieve(query)
