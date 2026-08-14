"""
RAG 服务模块：检索增强生成管线（LlamaIndex 版）

架构：
- config.py              全局配置（embedding、分块参数）
- ingestion/             离线：文档加载 → 清洗 → 分块 → 构建索引
- retrieval/             在线：混合检索 → 重排序 → 结果格式化
- knowledge/             领域知识：医学指标参考范围、缩写映射

核心接口：
- retrieve: 便捷检索函数（兼容旧接口）
- get_query_engine: 获取查询引擎单例
- build_index: 构建向量索引（离线使用）
"""

from rag.retrieval.query_engine import retrieve, get_query_engine

# 向后兼容：旧代码 from rag import retrieve_medical_knowledge 仍然可用
retrieve_medical_knowledge = retrieve


__all__ = [
    "retrieve",
    "retrieve_medical_knowledge",
    "get_query_engine",
]
