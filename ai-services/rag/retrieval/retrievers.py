"""
检索策略

封装三种检索方式：
1. 语义检索：把查询变成向量，去 PostgreSQL 里找最相似的文档
2. 关键词检索（BM25）：支持两种后端：
   - jieba + bm25s（本地，无需 ES）
   - Elasticsearch + IK（更准确，需要启动 ES）
3. 混合检索：把上面两种结果用 RRF 算法合并，两路都排名靠前的文档最终排名更高
"""

import logging
import os
from typing import List, Optional

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import BaseNode

from core.config import settings

logger = logging.getLogger(__name__)

# 停用词表：过滤掉没有检索意义的高频词
STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "他", "她", "它", "什么", "怎么", "如何", "哪些", "哪个", "那个",
    "方法", "可以", "能", "请", "问", "吗", "呢", "吧", "啊", "哦", "嗯",
    "哪", "谁", "为什么", "怎样", "怎么样", "多少", "几", "是不是", "有没有",
    "比较", "需要", "应该", "可能", "以及", "或者", "但是", "但", "如果", "因为",
    "所以", "而且", "虽然", "不过", "只是", "已经", "还是", "这个", "那个",
    "一下", "一些", "一般", "一样", "一种", "有关", "关于", "进行", "通过",
}


def create_vector_retriever(
    index: VectorStoreIndex,
    similarity_top_k: Optional[int] = None,
):
    """语义检索器。

    把查询变成向量 → 去 PostgreSQL (pgvector) 里找最近的 top_k 个向量。
    能搜到意思相近但用词不同的文档（如搜"肌酐偏高"能匹配到"血肌酐升高"）。
    """
    top_k = similarity_top_k or settings.RAG_TOP_K
    return index.as_retriever(similarity_top_k=top_k)


class ChineseBM25Retriever:
    """中文 BM25 检索器，使用 jieba 分词 + 医学词典。"""

    def __init__(self, nodes: List[BaseNode], similarity_top_k: int = 10):
        import jieba
        import bm25s

        self.nodes = nodes
        self.similarity_top_k = similarity_top_k

        # 加载医学自定义词典
        dict_path = os.path.join(os.path.dirname(__file__), "..", "elasticsearch", "medical_dict.dic")
        if os.path.exists(dict_path):
            jieba.load_userdict(dict_path)

        # 用 jieba 预分词
        corpus_tokens = []
        for node in nodes:
            text = node.get_content()
            tokens = [w for w in jieba.lcut(text) if w.strip()]
            corpus_tokens.append(tokens)

        # 构建 BM25 索引
        self.bm25 = bm25s.BM25()
        self.bm25.index(corpus_tokens, show_progress=False)

    def retrieve(self, query_bundle) -> List:
        import jieba
        from llama_index.core.schema import NodeWithScore

        query_str = query_bundle.query_str if hasattr(query_bundle, "query_str") else str(query_bundle)
        # 分词 + 过滤停用词（只保留有检索意义的词）
        query_tokens = [w for w in jieba.lcut(query_str) if w.strip() and w not in STOPWORDS]

        # 获取分数
        scores = self.bm25.get_scores(query_tokens)

        # 取 top_k
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:self.similarity_top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append(NodeWithScore(
                    node=self.nodes[idx],
                    score=float(scores[idx]),
                ))
        return results


def create_bm25_retriever(
    nodes: List[BaseNode],
    similarity_top_k: Optional[int] = None,
    use_es: bool = False,
):
    """关键词检索器（BM25）。

    支持两种后端：
    - use_es=False（默认）：jieba + bm25s，本地运行，无需外部服务
    - use_es=True：Elasticsearch + IK 分词器，更准确，需要启动 ES

    Args:
        nodes: 文档节点列表
        similarity_top_k: 返回 top K 个结果
        use_es: 是否使用 Elasticsearch
    """
    top_k = similarity_top_k or settings.RAG_TOP_K

    if use_es:
        from rag.elasticsearch.es_retriever import create_es_bm25_retriever
        return create_es_bm25_retriever(nodes=nodes, similarity_top_k=top_k)
    else:
        return ChineseBM25Retriever(nodes=nodes, similarity_top_k=top_k)


class HybridRetriever:
    """自定义混合检索器，使用纯 RRF（Reciprocal Rank Fusion）。

    RRF 只用排名，不用原始分数，避免 BM25 高分污染排序。
    公式：RRF_score(d) = Σ 1/(k + rank_i(d))，k=60 是常数。
    """

    def __init__(self, vector_retriever, bm25_retriever, similarity_top_k: int = 10, rrf_k: int = 60):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.similarity_top_k = similarity_top_k
        self.rrf_k = rrf_k

    def retrieve(self, query_bundle) -> List:
        from llama_index.core.schema import NodeWithScore

        # 两路检索，取更多候选以保证融合质量
        vec_results = self.vector_retriever.retrieve(query_bundle)
        bm25_results = self.bm25_retriever.retrieve(query_bundle)

        # 用 node_id 做 RRF 融合
        rrf_scores = {}  # node_id -> rrf_score
        node_map = {}    # node_id -> NodeWithScore（保留最佳原始信息）

        for rank, node_with_score in enumerate(vec_results):
            nid = node_with_score.node.node_id
            rrf_scores[nid] = rrf_scores.get(nid, 0) + 1.0 / (self.rrf_k + rank + 1)
            if nid not in node_map:
                node_map[nid] = node_with_score

        for rank, node_with_score in enumerate(bm25_results):
            nid = node_with_score.node.node_id
            rrf_scores[nid] = rrf_scores.get(nid, 0) + 1.0 / (self.rrf_k + rank + 1)
            if nid not in node_map:
                node_map[nid] = node_with_score

        # 按 RRF 分数降序排列
        sorted_ids = sorted(rrf_scores.keys(), key=lambda nid: rrf_scores[nid], reverse=True)

        results = []
        for nid in sorted_ids[:self.similarity_top_k]:
            original = node_map[nid]
            results.append(NodeWithScore(
                node=original.node,
                score=rrf_scores[nid],  # 用纯 RRF 分数
            ))

        return results


def create_hybrid_retriever(
    index: VectorStoreIndex,
    nodes: List[BaseNode],
    similarity_top_k: Optional[int] = None,
    num_queries: int = 1,
    use_es: bool = False,
):
    """混合检索器（语义 + 关键词）。

    同时用语义检索和关键词检索，然后用 RRF (Reciprocal Rank Fusion) 合并结果。
    RRF 只用排名不用原始分数，避免 BM25 高分污染排序。

    语义检索能搜到意思相近的文档，但可能漏掉精确关键词；
    关键词检索能精确命中，但搜不到同义词。
    两种互补，混合后效果更好。

    Args:
        use_es: 是否使用 Elasticsearch 做关键词检索（默认 False 用 jieba）
    """
    top_k = similarity_top_k or settings.RAG_TOP_K
    vector_retriever = create_vector_retriever(index, top_k)
    bm25_retriever = create_bm25_retriever(nodes, top_k, use_es=use_es)

    return HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        similarity_top_k=top_k,
    )
