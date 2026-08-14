"""
重排序器

使用 CrossEncoder 对检索结果进行语义重排序。
延迟加载模型，首次调用时才初始化。
"""

import logging
from typing import List, Optional

from llama_index.core.schema import NodeWithScore

from core.config import settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """CrossEncoder 重排序器（延迟加载）。

    与 LlamaIndex 的 SentenceTransformerRerank 功能相同，
    但使用自定义的延迟加载逻辑以兼容 ModelScope 下载。
    """

    def __init__(self):
        self._model = None

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True

        model_path = settings.RERANKER_MODEL_PATH
        device = settings.RERANKER_DEVICE

        try:
            from sentence_transformers import CrossEncoder
            logger.info("Reranker: loading CrossEncoder from %s on %s", model_path, device)
            self._model = CrossEncoder(
                model_path,
                device=device,
                trust_remote_code=True,
            )
            logger.info("Reranker: CrossEncoder loaded")
            return True
        except Exception as exc:
            logger.error("Reranker: load failed: %s", exc)
            return False

    @property
    def is_available(self) -> bool:
        return self._ensure_loaded()

    def rerank(
        self,
        query: str,
        nodes: List[NodeWithScore],
        top_k: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[NodeWithScore]:
        """对节点列表进行语义重排序。

        Args:
            query: 用户查询
            nodes: 检索到的 NodeWithScore 列表
            top_k: 返回的最大节点数
            threshold: 最低相关性分数阈值

        Returns:
            重排序后的 NodeWithScore 列表
        """
        if not nodes:
            return []

        if not self._ensure_loaded():
            logger.warning("Reranker not available, returning unfiltered nodes")
            return nodes[:top_k or settings.RERANKER_FINAL_K]

        top_k = top_k or settings.RERANKER_FINAL_K
        threshold = threshold if threshold is not None else settings.RERANKER_SCORE_THRESHOLD

        # 构建 (query, text) 对
        pairs = [(query, node.get_content()) for node in nodes]

        try:
            scores = self._model.predict(pairs, show_progress_bar=False)
        except Exception as exc:
            logger.error("Reranker: prediction failed: %s", exc)
            return nodes[:top_k]

        # 按分数排序、过滤
        scored = list(zip(scores, nodes))
        scored.sort(key=lambda x: x[0], reverse=True)

        result = []
        for score, node in scored:
            if score >= threshold:
                # 更新节点的分数
                node.score = float(score)
                result.append(node)
            if len(result) >= top_k:
                break

        logger.info(
            "Reranker: %d -> %d nodes | scores=[%s]",
            len(nodes),
            len(result),
            ", ".join(f"{s:.3f}" for s, _ in scored[:top_k]),
        )
        return result


# 模块级单例（延迟创建）
_reranker: Optional[CrossEncoderReranker] = None


def get_reranker() -> CrossEncoderReranker:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker
