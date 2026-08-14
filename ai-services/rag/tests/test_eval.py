"""
RAG 检索质量评估脚本（四阶段全评估）

逐阶段评估：
  1. BM25 关键词检索
  2. 向量语义检索
  3. 混合检索 RRF
  4. 重排序 CrossEncoder

每个阶段输出 top5 和 top10 的 Recall/Precision/MRR

使用方式：
    cd ai-services
    python -m rag.tests.test_eval
"""

import json
import logging
import math
import sys
from typing import Dict, List, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rag.eval")


# ============================================================
# 指标计算
# ============================================================

def recall_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / len(relevant_ids)


def precision_at_k(retrieved_ids: List[str], relevant_ids: Set[str], k: int) -> float:
    if k == 0:
        return 0.0
    return len(set(retrieved_ids[:k]) & relevant_ids) / k


def mrr(retrieved_ids: List[str], relevant_ids: Set[str]) -> float:
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


# ============================================================
# 四阶段检索
# ============================================================

def run_four_stages(question: str, engine, top_k: int = 10):
    """执行四阶段检索，返回每阶段的 node_id 列表。"""
    from llama_index.core.schema import QueryBundle
    from rag.retrieval.retrievers import (
        create_vector_retriever,
        create_bm25_retriever,
        create_hybrid_retriever,
    )

    engine._ensure_initialized()
    index = engine._index
    nodes = engine._nodes
    reranker = engine._reranker
    query_bundle = QueryBundle(query_str=question)

    # 1. BM25
    bm25 = create_bm25_retriever(nodes, similarity_top_k=top_k)
    bm25_results = bm25.retrieve(query_bundle)
    bm25_ids = [r.node.node_id for r in bm25_results]

    # 2. 向量检索
    vec = create_vector_retriever(index, similarity_top_k=top_k)
    vec_results = vec.retrieve(query_bundle)
    vec_ids = [r.node.node_id for r in vec_results]

    # 3. 混合检索 RRF（用更大的候选池）
    from core.config import settings
    recall_top_k = settings.RERANKER_TOP_K  # 40
    hybrid = create_hybrid_retriever(index, nodes, similarity_top_k=recall_top_k)
    hybrid_results = hybrid.retrieve(query_bundle)
    hybrid_ids = [r.node.node_id for r in hybrid_results]

    # 4. 重排序（从 hybrid top40 中选 top5）
    rerank_ids = []
    if reranker and reranker.is_available:
        rerank_results = reranker.rerank(question, hybrid_results, top_k=settings.RERANKER_FINAL_K)
        rerank_ids = [r.node.node_id for r in rerank_results]

    return {
        "bm25": bm25_ids,
        "vector": vec_ids,
        "hybrid": hybrid_ids,
        "rerank": rerank_ids,
    }


# ============================================================
# 评估
# ============================================================

def evaluate_all(test_file: str, k_values: List[int]):
    """评估整个测试集，四阶段全输出。"""
    from rag.config import init_llama_settings
    init_llama_settings()
    from rag.retrieval.query_engine import get_query_engine
    engine = get_query_engine()

    with open(test_file, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    logger.info("Loaded %d test cases", len(test_set))
    logger.info("")

    # 汇总
    stages = ["bm25", "vector", "hybrid", "rerank"]
    stage_names = {"bm25": "BM25", "vector": "向量", "hybrid": "混合RRF", "rerank": "重排序"}
    totals = {s: {"recall": {k: 0 for k in k_values}, "precision": {k: 0 for k in k_values}, "mrr": 0} for s in stages}
    num_cases = 0

    for i, case in enumerate(test_set):
        question = case["question"]
        relevant_ids = set(case.get("node", []))
        if not relevant_ids:
            continue

        num_cases += 1
        results = run_four_stages(question, engine, top_k=max(k_values))

        logger.info("=" * 70)
        logger.info("[%d] %s", i + 1, question)
        logger.info("    期望: %s", sorted(relevant_ids))
        logger.info("")

        for stage in stages:
            ids = results[stage]
            stage_mrr = mrr(ids, relevant_ids)
            totals[stage]["mrr"] += stage_mrr

            # 计算各 K 值指标
            metrics_str = []
            for k in k_values:
                r = recall_at_k(ids, relevant_ids, k)
                p = precision_at_k(ids, relevant_ids, k)
                totals[stage]["recall"][k] += r
                totals[stage]["precision"][k] += p
                metrics_str.append(f"R@{k}={r:.0%} P@{k}={p:.0%}")

            # 命中的 ID
            hits = [nid for nid in ids if nid in relevant_ids]
            hits_str = ",".join(hits) if hits else "无"

            logger.info("    %-6s | %s | MRR=%.2f | 命中: %s",
                       stage_names[stage], "  ".join(metrics_str), stage_mrr, hits_str)

        logger.info("")

    # 汇总报告
    logger.info("=" * 70)
    logger.info("汇总（%d 题平均）", num_cases)
    logger.info("=" * 70)
    logger.info("")

    for stage in stages:
        name = stage_names[stage]
        parts = []
        for k in k_values:
            avg_r = totals[stage]["recall"][k] / num_cases
            avg_p = totals[stage]["precision"][k] / num_cases
            parts.append(f"R@{k}={avg_r:.1%}  P@{k}={avg_p:.1%}")
        avg_mrr = totals[stage]["mrr"] / num_cases
        logger.info("  %-6s  %s  MRR=%.4f", name, "  ".join(parts), avg_mrr)

    logger.info("")
    logger.info("=" * 70)


if __name__ == "__main__":
    test_file = "rag/tests/test_set.json"
    evaluate_all(test_file, k_values=[5, 10])
