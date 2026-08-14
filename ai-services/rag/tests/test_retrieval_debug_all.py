"""
批量调试脚本 — 对测试集每个问题输出 BM25 / 向量 / 混合 / 重排序 四阶段结果

用法：
    cd ai-services
    python -m rag.tests.test_retrieval_debug_all --test-file rag/tests/test_set.json
    python -m rag.tests.test_retrieval_debug_all --test-file rag/tests/test_set.json --output debug_report.txt
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rag.debug_all")


def _init_engine():
    from rag.config import init_llama_settings
    init_llama_settings()
    from rag.retrieval.query_engine import get_query_engine
    engine = get_query_engine()
    engine._ensure_initialized()
    return engine


def retrieve_stages(question: str, engine, k: int = 10, _bm25_cache=None, _vec_cache=None):
    """对单个问题执行四阶段检索，返回各阶段结果。"""
    from llama_index.core.schema import QueryBundle, NodeWithScore
    from rag.retrieval.retrievers import (
        create_vector_retriever,
        create_bm25_retriever,
        create_hybrid_retriever,
    )
    from core.config import settings

    index = engine._index
    nodes = engine._nodes
    reranker = engine._reranker

    query_bundle = QueryBundle(query_str=question)

    # BM25（缓存）
    if _bm25_cache is None:
        _bm25_cache = create_bm25_retriever(nodes, similarity_top_k=k)
    bm25_nodes = _bm25_cache.retrieve(query_bundle)

    # 向量（缓存）
    if _vec_cache is None:
        _vec_cache = create_vector_retriever(index, similarity_top_k=k)
    vec_nodes = _vec_cache.retrieve(query_bundle)

    # 混合（缓存）
    recall_top_k = settings.RERANKER_TOP_K  # 40
    if engine._hybrid_retriever is None:
        engine._hybrid_retriever = create_hybrid_retriever(index, nodes, similarity_top_k=recall_top_k)
    hybrid_nodes = engine._hybrid_retriever.retrieve(query_bundle)

    # 重排序
    rerank_nodes = []
    if reranker and reranker.is_available:
        rerank_nodes = reranker.rerank(question, hybrid_nodes, top_k=settings.RERANKER_FINAL_K)

    def _extract(nodes_list):
        results = []
        for n in nodes_list:
            nid = n.node.id_ if hasattr(n, "node") else str(n.id_)
            score = n.score if n.score else 0.0
            meta = n.node.metadata if hasattr(n, "node") else n.metadata
            heading = meta.get("heading", "") if meta else ""
            text_preview = n.get_content()[:80].replace("\n", " ")
            results.append({"id": nid, "score": round(score, 4), "heading": heading, "text": text_preview})
        return results

    return {
        "bm25": _extract(bm25_nodes),
        "vector": _extract(vec_nodes),
        "hybrid": _extract(hybrid_nodes[:k]),
        "rerank": _extract(rerank_nodes),
        "_bm25_cache": _bm25_cache,
        "_vec_cache": _vec_cache,
    }


def format_question_report(idx: int, question: str, expected_ids: List[str], stages: dict) -> str:
    """格式化单个问题的报告。"""
    lines = []
    lines.append(f"{'='*80}")
    lines.append(f"[{idx+1}] 问题: {question}")
    lines.append(f"    期望节点: {expected_ids}")
    lines.append(f"{'='*80}")

    expected_set = set(expected_ids)

    for stage_name, label in [("bm25", "BM25 关键词检索"), ("vector", "向量语义检索"), ("hybrid", "混合检索 RRF"), ("rerank", "重排序 CrossEncoder")]:
        items = stages[stage_name]
        lines.append(f"\n  ── {label} (top {len(items)}) ──")
        for i, item in enumerate(items):
            marker = "✓" if item["id"] in expected_set else " "
            lines.append(f"    {marker} [{i+1:>2}] #{item['id']:<6} score={item['score']:.4f}  {item['heading'][:55]}")

        # 统计命中
        retrieved_ids = set(item["id"] for item in items)
        hits = retrieved_ids & expected_set
        lines.append(f"    命中: {len(hits)}/{len(expected_set)} 个 | 命中ID: {hits if hits else '无'}")

    # 重叠分析
    bm25_ids = set(item["id"] for item in stages["bm25"])
    vec_ids = set(item["id"] for item in stages["vector"])
    rerank_ids = set(item["id"] for item in stages["rerank"])
    lines.append(f"\n  ── 重叠分析 ──")
    lines.append(f"    BM25 ∩ 向量 = {len(bm25_ids & vec_ids)} | 仅BM25={len(bm25_ids - vec_ids)} | 仅向量={len(vec_ids - bm25_ids)}")
    lines.append(f"    重排命中: {len(rerank_ids & expected_set)}/{len(expected_set)}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RAG 检索批量调试")
    parser.add_argument("--test-file", required=True, help="测试集 JSON 文件")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径（默认打印到终端）")
    parser.add_argument("--k", type=int, default=10, help="每个阶段显示 top K")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个问题")
    args = parser.parse_args()

    with open(args.test_file, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    if args.limit:
        test_set = test_set[:args.limit]

    logger.info("Initializing engine...")
    engine = _init_engine()
    logger.info("Engine ready. Processing %d questions...\n", len(test_set))

    output_lines = []
    bm25_cache = None
    vec_cache = None
    for i, case in enumerate(test_set):
        question = case["question"]
        expected_ids = case.get("node", case.get("relevant_ids", []))

        logger.info("[%d/%d] %s", i+1, len(test_set), question)
        stages = retrieve_stages(question, engine, k=args.k, _bm25_cache=bm25_cache, _vec_cache=vec_cache)
        bm25_cache = stages.pop("_bm25_cache")
        vec_cache = stages.pop("_vec_cache")
        report = format_question_report(i, question, expected_ids, stages)
        output_lines.append(report)

    full_report = "\n".join(output_lines)

    if args.output:
        Path(args.output).write_text(full_report, encoding="utf-8")
        logger.info("Report saved to %s", args.output)
    else:
        print(full_report)


if __name__ == "__main__":
    main()
