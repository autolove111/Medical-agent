"""
RAG 服务模块：检索增强生成管线

核心能力：
- RAGSystem: RAG 主编排器（单例，线程安全）
- retrieve_medical_knowledge: 便捷检索函数
- HybridRetriever: 混合检索（关键词 + 语义 + 重排序）
- BCEFlagEmbedding: 本地嵌入模型
- RAGCache: Redis 缓存
"""

from service.rag.rag import retrieve_medical_knowledge


__all__ = [
    "RAGSystem",
    "retrieve_medical_knowledge",
]
