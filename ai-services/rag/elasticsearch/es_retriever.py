"""
Elasticsearch BM25 检索器

使用 ES + IK 分词器替代 jieba + bm25s，提供更准确的中文关键词检索。
"""

import logging
import os
from typing import List, Optional

from llama_index.core.schema import BaseNode, NodeWithScore

logger = logging.getLogger(__name__)

ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX = "medical_knowledge"


class ESBM25Retriever:
    """基于 Elasticsearch 的 BM25 检索器。

    使用 IK 分词器（ik_max_word 模式）进行中文分词，
    比 jieba 更适合医学文献检索。
    """

    def __init__(
        self,
        nodes: List[BaseNode],
        similarity_top_k: int = 10,
        es_host: str = ES_HOST,
        es_index: str = ES_INDEX,
    ):
        self.nodes = nodes
        self.similarity_top_k = similarity_top_k
        self.es_host = es_host
        self.es_index = es_index

        # 构建 node_id -> node 映射
        self._node_map = {}
        for node in nodes:
            nid = node.node_id if hasattr(node, "node_id") else node.id_
            self._node_map[str(nid)] = node

        # 延迟连接 ES（首次查询时连接）
        self._es = None

    def _get_es(self):
        """获取 ES 客户端（延迟初始化）。"""
        if self._es is None:
            from elasticsearch import Elasticsearch
            self._es = Elasticsearch(self.es_host)
            if not self._es.ping():
                raise ConnectionError(f"Cannot connect to ES at {self.es_host}")
        return self._es

    def retrieve(self, query_bundle) -> List[NodeWithScore]:
        """执行 ES BM25 检索。"""
        query_str = query_bundle.query_str if hasattr(query_bundle, "query_str") else str(query_bundle)

        es = self._get_es()

        # 使用 match 查询 + IK 分词
        body = {
            "query": {
                "match": {
                    "text": {
                        "query": query_str,
                        "analyzer": "smartcn_tokenizer",
                    }
                }
            },
            "size": self.similarity_top_k,
            "_source": ["node_id", "text", "heading"],
        }

        try:
            resp = es.search(index=self.es_index, body=body)
        except Exception as e:
            logger.warning("ES search failed: %s", e)
            return []

        results = []
        for hit in resp["hits"]["hits"]:
            nid = hit["_source"]["node_id"]
            score = hit["_score"]

            # 从 node_map 中找到对应的 node
            node = self._node_map.get(nid)
            if node is None:
                # 如果 node_map 中没有，跳过
                continue

            results.append(NodeWithScore(
                node=node,
                score=float(score),
            ))

        return results


def create_es_bm25_retriever(
    nodes: List[BaseNode],
    similarity_top_k: Optional[int] = None,
    es_host: str = ES_HOST,
    es_index: str = ES_INDEX,
) -> ESBM25Retriever:
    """创建 ES BM25 检索器。"""
    from core.config import settings
    top_k = similarity_top_k or settings.RAG_TOP_K
    return ESBM25Retriever(
        nodes=nodes,
        similarity_top_k=top_k,
        es_host=es_host,
        es_index=es_index,
    )
