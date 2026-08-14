"""
RAG 检索调试脚本 — 逐阶段查看 BM25 / 向量 / 混合 / 重排序 的结果

用法：
    cd ai-services
    python -m rag.tests.test_retrieval_debug --question "肾小球疾病的发病机制是什么？"
    python -m rag.tests.test_retrieval_debug --test-file rag/tests/test_set.json --index 0
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rag.debug")


def _init_engine():
    """初始化一次引擎，返回 (engine, index, nodes, reranker)"""
    from rag.config import init_llama_settings
    init_llama_settings()

    from rag.retrieval.query_engine import get_query_engine
    from rag.config import create_reranker
    engine = get_query_engine()

    # 从 engine 内部取出 index / nodes / reranker
    engine._ensure_initialized()
    return engine


def run_debug(question: str, engine, k: int = 10):
    """对单个问题执行四阶段检索，逐阶段打印结果。"""
    from llama_index.core.schema import QueryBundle, NodeWithScore
    from rag.retrieval.retrievers import (
        create_vector_retriever,
        create_bm25_retriever,
        create_hybrid_retriever,
    )
    from rag.retrieval.rerankers import get_reranker
    from core.config import settings

    index = engine._index
    nodes = engine._nodes
    reranker = engine._reranker

    query_bundle = QueryBundle(query_str=question)

    # ── 阶段 1: BM25 ──
    bm25 = create_bm25_retriever(nodes, similarity_top_k=k)
    bm25_nodes = bm25.retrieve(query_bundle)

    # ── 阶段 2: 向量检索 ──
    vec = create_vector_retriever(index, similarity_top_k=k)
    vec_nodes = vec.retrieve(query_bundle)

    # ── 阶段 3: 混合检索 (RRF) ──
    # QueryFusionRetriever 内部同时跑 BM25 + 向量，再 RRF 合并
    # 我们用更大的 top_k 来模拟 RERANKER_TOP_K 的召回量
    recall_top_k = settings.RERANKER_TOP_K  # 40
    hybrid = create_hybrid_retriever(index, nodes, similarity_top_k=recall_top_k)
    hybrid_nodes = hybrid.retrieve(query_bundle)

    # ── 阶段 4: 重排序 ──
    rerank_nodes = []
    if reranker and reranker.is_available:
        rerank_nodes = reranker.rerank(
            question,
            hybrid_nodes,
            top_k=settings.RERANKER_FINAL_K,  # 10
        )

    # ── 格式化输出 ──
    def _fmt(nodes_list, label, top_n=None):
        items = nodes_list[:top_n] if top_n else nodes_list
        lines = []
        for i, n in enumerate(items):
            nid = n.node.id_ if hasattr(n, "node") else str(n.id_)
            score = n.score if n.score else 0.0
            meta = n.node.metadata if hasattr(n, "node") else n.metadata
            heading = meta.get("heading", "") if meta else ""
            text = n.get_content()[:80].replace("\n", " ")
            lines.append(f"  [{i+1:>2}] #{nid:<6} score={score:.4f}  {heading[:50]}")
        return "\n".join(lines)

    print(f"\n{'='*80}")
    print(f"问题: {question}")
    print(f"{'='*80}")

    print(f"\n── BM25 (top {k}) ──")
    print(_fmt(bm25_nodes, "BM25"))

    print(f"\n── 向量检索 (top {k}) ──")
    print(_fmt(vec_nodes, "向量"))

    print(f"\n── 混合检索 RRF (top {recall_top_k}) ──")
    print(_fmt(hybrid_nodes, "混合", top_n=k))

    print(f"\n── 重排序 (top {settings.RERANKER_FINAL_K}) ──")
    print(_fmt(rerank_nodes, "重排"))

    # ── 重叠分析 ──
    bm25_ids = set(n.node.id_ if hasattr(n, "node") else n.id_ for n in bm25_nodes[:k])
    vec_ids  = set(n.node.id_ if hasattr(n, "node") else n.id_ for n in vec_nodes[:k])
    hybrid_ids = set(n.node.id_ if hasattr(n, "node") else n.id_ for n in hybrid_nodes[:k])
    rerank_ids = set(n.node.id_ if hasattr(n, "node") else n.id_ for n in rerank_nodes)

    print(f"\n── 重叠分析 ──")
    print(f"  BM25 ∩ 向量  = {len(bm25_ids & vec_ids)} 个")
    print(f"  BM25 ∩ 混合  = {len(bm25_ids & hybrid_ids)} 个")
    print(f"  向量 ∩ 混合  = {len(vec_ids & hybrid_ids)} 个")
    print(f"  混合 ∩ 重排  = {len(hybrid_ids & rerank_ids)} 个")
    print(f"  仅 BM25 有   = {len(bm25_ids - vec_ids)} 个: {bm25_ids - vec_ids}")
    print(f"  仅 向量 有   = {len(vec_ids - bm25_ids)} 个: {vec_ids - bm25_ids}")

    return {
        "bm25": [n.node.id_ if hasattr(n, "node") else n.id_ for n in bm25_nodes],
        "vector": [n.node.id_ if hasattr(n, "node") else n.id_ for n in vec_nodes],
        "hybrid": [n.node.id_ if hasattr(n, "node") else n.id_ for n in hybrid_nodes],
        "rerank": [n.node.id_ if hasattr(n, "node") else n.id_ for n in rerank_nodes],
    }


def main():
    parser = argparse.ArgumentParser(description="RAG 检索阶段调试")
    parser.add_argument("--question", "-q", type=str, help="单个查询问题")
    parser.add_argument("--test-file", type=str, help="测试集 JSON 文件")
    parser.add_argument("--index", type=int, default=0, help="从测试集中选第几个问题 (0-based)")
    parser.add_argument("--k", type=int, default=10, help="每个阶段显示 top K")
    args = parser.parse_args()

    if args.question:
        question = args.question
    elif args.test_file:
        with open(args.test_file, "r", encoding="utf-8") as f:
            test_set = json.load(f)
        if args.index >= len(test_set):
            print(f"Index {args.index} out of range (max {len(test_set)-1})")
            return
        question = test_set[args.index]["question"]
    else:
        print("请指定 --question 或 --test-file")
        return

    logger.info("Initializing engine (one-time)...")
    engine = _init_engine()
    logger.info("Engine ready. Running debug retrieval...\n")

    run_debug(question, engine, k=args.k)


if __name__ == "__main__":
    main()
