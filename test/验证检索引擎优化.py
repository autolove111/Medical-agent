"""
检索引擎优化验证脚本
~~~~~~~~~~~~~~~~~~~
逐项验证：查询改写 → 关键词匹配 → 语义检索 → 重排序截断 → Agent 集成。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

# 强制重载
for m in list(sys.modules):
    if any(p in m for p in ("harness", "service", "core")):
        del sys.modules[m]


def test_query_rewrite():
    """验证 1：查询改写"""
    from service.rag.query_rewriter import rewrite_query, extract_keywords, _extract_indicators

    print("=" * 60)
    print("  验证1：查询改写")
    print("=" * 60)

    cases = [
        ("我血糖偏高怎么办", ["glu", "偏高", "怎么办"]),
        ("肌酐120正常吗", ["cr", "正常"]),
        ("ALT升高是什么意思", ["alt", "升高", "什么意思"]),
        ("最近头晕没劲", ["头晕", "乏力"]),
    ]

    for user_input, expected_kw in cases:
        rewritten = rewrite_query(user_input)
        keywords = extract_keywords(user_input)
        indicators = _extract_indicators(user_input)
        ok = all(ek in keywords for ek in expected_kw)
        print(f"  输入: {user_input}")
        print(f"  改写: {rewritten[:100]}...")
        print(f"  关键词: {keywords}")
        print(f"  指标: {indicators}")
        print(f"  结果: {'PASS' if ok else 'FAIL'}")
        print()


def test_reference_match():
    """验证 2：reference_ranges 关键词匹配"""
    from service.rag.hybrid_retriever import _match_reference_ranges
    from service.rag.query_rewriter import extract_keywords

    print("=" * 60)
    print("  验证2：关键词匹配（reference_ranges）")
    print("=" * 60)

    # 精确指标缩写
    query1 = "Cr偏高是什么意思"
    docs1 = _match_reference_ranges(query1, extract_keywords(query1))
    print(f"  查询: {query1}")
    print(f"  匹配文档: {len(docs1)} 篇")
    for d in docs1:
        print(f"    来源: {d.metadata.get('source')}, 长度: {len(d.page_content)} 字符")
    print(f"  结果: {'PASS' if len(docs1) >= 1 else 'FAIL'}")

    # 中文指标名
    query2 = "白细胞偏低的原因"
    docs2 = _match_reference_ranges(query2, extract_keywords(query2))
    print(f"  查询: {query2}")
    print(f"  匹配文档: {len(docs2)} 篇")
    for d in docs2:
        print(f"    来源: {d.metadata.get('source')}, 长度: {len(d.page_content)} 字符")
    print(f"  结果: {'PASS' if len(docs2) >= 1 else 'FAIL'}")
    print()


def test_hybrid_search():
    """验证 3：混合检索 vs 纯语义检索"""
    from service.rag.rag import get_rag_system
    from service.rag.hybrid_retriever import HybridRetriever

    print("=" * 60)
    print("  验证3：混合检索（关键词 + 语义 + 重排序）")
    print("=" * 60)

    rag = get_rag_system()
    faiss_retriever = rag._get_faiss_retriever()

    if faiss_retriever is None:
        print("  FAISS retriever 不可用，跳过")
        return

    if rag.hybrid_retriever is None:
        rag.hybrid_retriever = HybridRetriever(faiss_retriever)

    query = "血肌酐120偏高怎么办 饮食建议"
    print(f"  查询: {query}")

    # 纯语义检索
    from service.rag.rag_formatter import format_documents_as_answer
    faiss_docs = list(faiss_retriever.invoke(query))
    print(f"  纯语义检索: {len(faiss_docs)} 篇")
    for d in faiss_docs:
        src = d.metadata.get("source", "?")
        print(f"    来源: {src}, 长度: {len(d.page_content)} 字符")

    # 混合检索
    hybrid_docs, meta = rag.hybrid_retriever.hybrid_search(query, top_k=5)
    print(f"  混合检索: {len(hybrid_docs)} 篇")
    print(f"    改写后查询: {str(meta.get('query_rewritten', ''))[:100]}")
    print(f"    reference_ranges 匹配: {meta.get('ref_docs', 0)} 篇")
    print(f"    FAISS 语义检索: {meta.get('faiss_docs', 0)} 篇")
    for d in hybrid_docs:
        src = d.metadata.get("source", "?")
        print(f"    来源: {src}, 长度: {len(d.page_content)} 字符")

    has_ref = any("reference_ranges" in d.metadata.get("source", "") for d in hybrid_docs)
    is_reranked = len(hybrid_docs) <= 5 and all(
        len(d.page_content) <= 700 for d in hybrid_docs  # 600 + 截断标记
    )
    print(f"  包含参考范围: {'PASS' if has_ref else 'FAIR (FAISS-only)'}")
    print(f"  重排序截断: {'PASS' if is_reranked else 'FAIL'}")
    print(f"  结果: {'PASS' if has_ref and is_reranked else 'FAIR'}")
    print()


def test_end_to_end():
    """验证 4：Agent 端到端（混合检索注入 prompt）"""
    from harness.llm_adapter.create_agent import create_agent

    print("=" * 60)
    print("  验证4：Agent 端到端（含混合检索）")
    print("=" * 60)

    agent = create_agent(
        user_id="tester",
        user_name="测试",
        user_age=40,
        user_gender="男",
        max_new_tokens=256,
    )

    query = "肌酐120 饮食注意什么"
    print(f"  用户: {query}")
    reply = agent.chat(query)

    # 检查 rag_context
    rag_ctx = agent.state.rag_context
    has_ref = "参考范围" in rag_ctx or "μmol/L" in rag_ctx or "mmol/L" in rag_ctx
    has_truncation = any(len(d.page_content) <= 700 for d in [])  # can't check docs directly
    # Check if reply references specific knowledge
    has_specific = any(kw in reply for kw in ["μmol", "肌酐", "肾脏", "蛋白", "饮食"])

    print(f"  RAG上下文长度: {len(rag_ctx)} 字符")
    print(f"  RAG含参考范围: {'PASS' if has_ref else 'FAIR'}")
    print(f"  回复含专业知识: {'PASS' if has_specific else 'FAIR'}")
    print(f"  回复片段: {reply[:200]}...")
    print(f"  结果: {'PASS' if has_ref and has_specific else 'FAIR'}")
    print()


def main():
    print()
    print("=" * 60)
    print("  检索引擎优化 - 完整验证")
    print("=" * 60)
    print()

    test_query_rewrite()
    test_reference_match()
    test_hybrid_search()
    test_end_to_end()

    print("=" * 60)
    print("  验证完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
