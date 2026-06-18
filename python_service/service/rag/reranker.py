"""
Cross-Encoder Reranker for medical RAG retrieval.

Replaces the coarse keyword-hit scoring in hybrid_retriever with
semantic relevance scoring via a Cross-Encoder model (bge-reranker-base).

Load priority: local models/ → ModelScope → HuggingFace (fallback)
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from core.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Semantic reranker using a Cross-Encoder model.

    Lazy-loads the model on first use to avoid blocking startup.
    Supports ModelScope auto-download for China-friendly access.

    Usage:
        reranker = CrossEncoderReranker()
        ranked = reranker.rerank(query, docs, top_k=5, threshold=0.35)
    """

    def __init__(self):
        self._model = None
        self._model_path: Optional[str] = None

    # ── lazy load ─────────────────────────────────────────

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True

        model_path = settings.RERANKER_MODEL_PATH
        device = settings.RERANKER_DEVICE

        # 1) Check local path
        if os.path.isdir(model_path):
            resolved = model_path
            logger.info("Reranker: using local model %s", resolved)
        else:
            # 2) Try ModelScope download
            resolved = self._download_from_modelscope(model_path)
            if resolved is None:
                # 3) Fallback: treat model_path as HuggingFace ID
                logger.info("Reranker: trying HuggingFace ID %s", model_path)
                resolved = model_path

        try:
            from sentence_transformers import CrossEncoder
            logger.info("Reranker: loading CrossEncoder from %s on %s ...", resolved, device)
            self._model = CrossEncoder(
                resolved,
                device=device,
                trust_remote_code=True,
            )
            self._model_path = resolved
            logger.info("Reranker: CrossEncoder loaded successfully")
            return True
        except Exception as exc:
            logger.error("Reranker: failed to load model: %s", exc)
            return False

    @staticmethod
    def _download_from_modelscope(model_path: str) -> Optional[str]:
        """Try to download the model from ModelScope."""
        try:
            from modelscope import snapshot_download

            # Map HuggingFace ID → ModelScope ID
            ms_id = model_path
            if "bge-reranker" in model_path.lower():
                # BAAI/bge-reranker-base → Xorbits/bge-reranker-base
                # BAAI/bge-reranker-v2-m3 → Xorbits/bge-reranker-v2-m3
                ms_id = model_path.replace("BAAI", "Xorbits")

            cache_dir = os.path.dirname(model_path) if os.path.isabs(model_path) else os.path.join(
                os.path.dirname(settings.RERANKER_MODEL_PATH), ".."
            )
            cache_dir = os.path.abspath(cache_dir)

            logger.info("Reranker: downloading from ModelScope: %s → %s", ms_id, cache_dir)
            local = snapshot_download(ms_id, cache_dir=cache_dir)
            logger.info("Reranker: ModelScope download complete → %s", local)
            return local
        except ImportError:
            logger.debug("Reranker: modelscope not installed")
        except Exception as exc:
            logger.warning("Reranker: ModelScope download failed: %s", exc)
        return None

    # ── public API ────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return self._ensure_loaded()

    def rerank(
        self,
        query: str,
        docs: list,
        top_k: int = 5,
        threshold: float = 0.35,
    ) -> List:
        """Rerank documents by Cross-Encoder semantic relevance.

        Args:
            query:     User query text.
            docs:      List of LangChain Document objects.
            top_k:     Maximum number of documents to return.
            threshold: Minimum relevance score (0.0–1.0). Docs below are discarded.

        Returns:
            Ranked list of Documents (highest score first), length ≤ top_k.
            Returns empty list if reranker unavailable or no docs pass threshold.
        """
        if not docs:
            return []

        if not self._ensure_loaded():
            logger.warning("Reranker: model not available, returning unfiltered docs")
            return docs[:top_k]

        # Build (query, doc) pairs
        pairs = [(query, doc.page_content) for doc in docs]

        try:
            scores = self._model.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            logger.error("Reranker: prediction failed: %s", exc)
            return docs[:top_k]

        # Zip, sort, filter
        scored = list(zip(scores, docs))
        scored.sort(key=lambda x: x[0], reverse=True)

        result = []
        for score, doc in scored:
            if score >= threshold:
                result.append(doc)
            if len(result) >= top_k:
                break

        logger.info(
            "Reranker: %d docs → %d after rerank | scores=[%s]",
            len(docs),
            len(result),
            ", ".join(f"{s:.3f}" for s, _ in scored[:top_k]),
        )

        return result


# ── module-level singleton (lazy) ─────────────────────────

_reranker: Optional[CrossEncoderReranker] = None


def get_reranker() -> CrossEncoderReranker:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker
