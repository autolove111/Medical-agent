"""
hybrid_retriever
~~~~~~~~~~~~~~~~
混合检索引擎：关键词匹配 + FAISS 语义检索 + 重排序 + 截断。

三层检索：
1. reference_ranges 精确匹配 → 指标参考范围（结构化数据）
2. FAISS 语义检索 → 医学知识文档（非结构化文本）
3. 结果合并 → 去重 → 按关键词命中率重排序 → 截断过长文档
"""

import logging
from typing import List, Dict, Tuple, Optional

from langchain_core.documents import Document

from knowledge.reference_ranges import REFERENCE_RANGES, format_reference_text
from knowledge.query_rewriter import rewrite_query, extract_keywords

logger = logging.getLogger(__name__)

MAX_DOC_LENGTH = 600  # 单篇文档最大字符数（超过则截断）


# ============================================================
# 关键词匹配层：从 reference_ranges 检索
# ============================================================

def _match_reference_ranges(query: str, keywords: List[str]) -> List[Document]:
    """
    在 REFERENCE_RANGES 中按关键词精确匹配。
    三层匹配：
    1. 精确代码匹配（Cr/WBC/ALT 等）
    2. 中文指标名匹配
    3. 系统关键词 → 返回该系统下最相关的前几个指标
    最多返回 5 个文档。
    """
    matched: List[Document] = []
    query_lower = query.lower()

    # 中文指标名 → 代码（复用 query_rewriter 的映射）
    cn_to_code = {
        "肌酐": "cr", "尿酸": "ua", "尿素": "urea", "尿素氮": "bun", "肾小球滤过率": "egfr",
        "血糖": "glu", "糖化血红蛋白": "hba1c",
        "血红蛋白": "hb", "白细胞": "wbc", "红细胞": "rbc", "血小板": "plt",
        "转氨酶": "alt", "胆红素": "tbil", "总蛋白": "tp", "白蛋白": "alb",
        "胆固醇": "chol", "甘油三酯": "tg", "高密度脂蛋白": "hdl", "低密度脂蛋白": "ldl",
        "钠": "na", "钾": "k", "钙": "ca", "氯": "cl", "镁": "mg", "磷": "p",
        "肌酸激酶": "ck", "肌钙蛋白": "troponin", "C反应蛋白": "crp",
        "促甲状腺激素": "tsh", "甲状腺素": "t4",
    }

    # 系统关键词 → 该系统的关键指标（最多 3 个）
    system_indicators = {
        "肾功能": ["cr", "bun", "egfr"],
        "肝功能": ["alt", "ast", "tbil"],
        "血脂": ["chol", "tg", "ldl"],
        "电解质": ["na", "k", "ca"],
        "甲状腺": ["tsh", "t3", "t4"],
        "血常规": ["wbc", "rbc", "hb", "plt"],
        "心肌": ["ck", "troponin", "bnp"],
    }

    codes_to_add = set()

    # Layer 1: 精确代码匹配
    for code in REFERENCE_RANGES:
        if code.lower() in query_lower:
            codes_to_add.add(code.lower())

    # Layer 2: 中文指标名匹配
    for cn_name, code in cn_to_code.items():
        if cn_name in query:
            codes_to_add.add(code)

    # Layer 3: 系统关键词匹配（最多加 3 个）
    for sys_name, codes in system_indicators.items():
        if sys_name in query:
            for c in codes[:3]:
                codes_to_add.add(c)

    # 创建 Document（最多 5 个）
    for code in list(codes_to_add)[:5]:
        # 查找正确的大小写键
        ref_key = None
        for key in REFERENCE_RANGES:
            if key.lower() == code.lower():
                ref_key = key
                break
        if ref_key:
            text = format_reference_text(ref_key)
            doc = Document(
                page_content=text,
                metadata={"source": f"reference_ranges/{ref_key}", "type": "reference_range"}
            )
            matched.append(doc)

    if matched:
        logger.info("Reference match: %d indicators | codes=%s", len(matched), list(codes_to_add)[:5])

    return matched


# ============================================================
# 语义检索层：FAISS 向量检索
# ============================================================

def _semantic_search(query: str, retriever, top_k: int = 5) -> List[Document]:
    """FAISS 语义检索，返回 top_k 篇文档"""
    try:
        docs = list(retriever.invoke(query))
        if len(docs) > top_k:
            docs = docs[:top_k]
        return docs
    except Exception as exc:
        logger.warning("Semantic search failed: %s", exc)
        return []


# ============================================================
# 重排序：按关键词命中率加权
# ============================================================

def _keyword_score(doc: Document, keywords: List[str]) -> float:
    """
    计算文档与关键词的匹配分数。
    每个匹配的关键词 +1 分，指标缩写匹配 +2 分。
    """
    if not keywords:
        return 0.0

    content = doc.page_content.lower()
    score = 0.0
    for kw in keywords:
        if kw.lower() in content:
            # 指标缩写（短关键词，精确匹配）权重更高
            score += 2.0 if len(kw) <= 5 else 1.0

    # 归一化到 [0, 1]
    max_possible = sum(2.0 if len(kw) <= 5 else 1.0 for kw in keywords)
    return score / max_possible if max_possible > 0 else 0.0


def _deduplicate_docs(docs: List[Document]) -> List[Document]:
    """按 page_content 前 100 字符去重"""
    seen = set()
    result = []
    for doc in docs:
        fingerprint = doc.page_content[:100].strip()
        if fingerprint not in seen:
            seen.add(fingerprint)
            result.append(doc)
    return result


def _truncate_doc(doc: Document, max_len: int = MAX_DOC_LENGTH) -> Document:
    """截断过长文档，保留前 max_len 字符"""
    content = doc.page_content
    if len(content) <= max_len:
        return doc

    # 在句号或换行处截断，避免截断在词语中间
    truncated = content[:max_len]
    last_break = max(truncated.rfind("。"), truncated.rfind("\n"), truncated.rfind(". "))
    if last_break > max_len // 2:
        truncated = truncated[:last_break + 1]

    return Document(
        page_content=truncated + "\n...(内容已截断)",
        metadata=doc.metadata,
    )


def rerank_and_truncate(
    docs: List[Document],
    keywords: List[str],
    max_docs: int = 5,
    max_len: int = MAX_DOC_LENGTH,
) -> List[Document]:
    """
    重排序 + 去重 + 截断：
    1. 按关键词命中率降序排列
    2. 去重（按内容指纹）
    3. 截断过长文档
    4. 返回 top max_docs
    """
    # 计算分数
    scored: List[Tuple[float, Document]] = []
    for doc in docs:
        score = _keyword_score(doc, keywords)
        scored.append((score, doc))

    # 按分数降序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 去重
    seen = set()
    ranked = []
    for score, doc in scored:
        fingerprint = doc.page_content[:100].strip()
        if fingerprint not in seen:
            seen.add(fingerprint)
            ranked.append(doc)

    # 截断
    ranked = [_truncate_doc(doc, max_len) for doc in ranked]

    # 限制数量
    ranked = ranked[:max_docs]

    if ranked:
        scores_str = ", ".join(
            f"{_keyword_score(d, keywords):.2f}" for d in ranked
        )
        logger.info(
            "Reranked %d docs | scores=[%s] | keywords=%s",
            len(ranked), scores_str, keywords,
        )

    return ranked


# ============================================================
# 混合检索主入口
# ============================================================

class HybridRetriever:
    """
    混合检索器：整合关键词匹配 + 语义检索 + 重排序。

    使用方式：
        retriever = HybridRetriever(faiss_retriever)
        docs = retriever.hybrid_search("肌酐120偏高怎么办")
    """

    def __init__(self, faiss_retriever):
        self.faiss_retriever = faiss_retriever

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        use_query_rewrite: bool = True,
    ) -> Tuple[List[Document], Dict[str, object]]:
        """
        执行混合检索。

        参数：
            query: 用户原始查询
            top_k: 最终返回文档数
            use_query_rewrite: 是否使用查询改写

        返回：
            (documents, meta)：文档列表 + 元信息（含关键词、检索来源等）
        """
        keywords = extract_keywords(query)
        meta: Dict[str, object] = {
            "original_query": query,
            "keywords": keywords,
            "ref_docs": 0,
            "faiss_docs": 0,
            "query_rewritten": query,
        }

        # Step 1: 查询改写
        if use_query_rewrite:
            rewritten = rewrite_query(query)
            if rewritten != query:
                meta["query_rewritten"] = rewritten
                logger.info("Query rewritten: '%s' -> '%s'", query[:60], rewritten[:120])

        search_query = str(meta["query_rewritten"])

        # Step 2: 关键词匹配（reference_ranges）
        ref_docs = _match_reference_ranges(search_query, keywords)
        meta["ref_docs"] = len(ref_docs)
        logger.info("Reference range match: %d docs", len(ref_docs))

        # Step 3: 语义检索（FAISS）
        faiss_docs = _semantic_search(search_query, self.faiss_retriever, top_k=top_k)
        meta["faiss_docs"] = len(faiss_docs)
        logger.info("FAISS semantic search: %d docs", len(faiss_docs))

        # Step 4: 合并去重
        all_docs = ref_docs + faiss_docs
        all_docs = _deduplicate_docs(all_docs)

        # Step 5: 重排序 + 截断
        ranked = rerank_and_truncate(all_docs, keywords, max_docs=top_k)

        logger.info(
            "Hybrid search result: %d docs (ref=%d + faiss=%d) -> %d ranked",
            len(all_docs), meta["ref_docs"], meta["faiss_docs"], len(ranked),
        )

        return ranked, meta
