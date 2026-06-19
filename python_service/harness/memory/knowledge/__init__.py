"""
knowledge 模块：医学知识数据层

包含：
- reference_ranges: 40+ 种检验指标的参考范围（静态数据）
- medical_knowledge: KnowledgeBase 兼容层（轻量级知识查询）
- data/: 知识文档和向量库数据文件
"""

from .reference_ranges import REFERENCE_RANGES, get_reference_range, format_reference_text

__all__ = [
    "REFERENCE_RANGES",
    "get_reference_range",
    "format_reference_text"
]
