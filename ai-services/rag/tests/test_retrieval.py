"""
RAG 检索流水线测试

测试步骤：
  Step 1: 混合检索（语义 + BM25）
  Step 2: 重排序

使用方式：
    cd ai-services
    python -m rag.tests.test_retrieval
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("test_retrieval")

# 测试用例
TEST_QUERIES = [
    "肌酐偏高怎么办",
    # "血糖高是什么原因",
    # "白细胞低有什么危害",
]


def _banner(text, char="═", width=60):
    logger.info("")
    logger.info(char * width)
    logger.info("  %s", text)
    logger.info(char * width)


def _section(text, char="─", width=50):
    logger.info("")
    logger.info("  %s %s", char * 3, text)
    logger.info("  %s", char * width)


def _node_block(index, score, content):
    lines = content.strip().split("\n")
    logger.info("    ┌─ #%d  score: %.4f ──────────────────────", index, score)
    for line in lines:
        logger.info("    │ %s", line)
    logger.info("    └──────────────────────────────────────")


def test_step1_retrieval():
    """Step 1: 混合检索"""
    _banner("STEP 1: 混合检索（语义 + BM25）")

    from rag.config import init_llama_settings
    init_llama_settings()

    from rag.retrieval.retrievers import create_vector_retriever, create_bm25_retriever, create_hybrid_retriever
    from rag.ingestion.index_builder import load_index
    from llama_index.core.schema import QueryBundle, TextNode
    import psycopg2

    # 加载
    index = load_index()
    if index is None:
        logger.error("❌ 索引未找到，请先运行构建")
        return

    conn = psycopg2.connect(
        host="localhost", port=5432,
        database="medlab_db",
        user="medlab_user", password="medlab_password"
    )
    cur = conn.cursor()
    cur.execute("SELECT node_id, text, metadata_ FROM data_knowledge_vectors")
    rows = cur.fetchall()
    conn.close()
    nodes = [TextNode(id_=nid, text=txt, metadata=meta or {}) for nid, txt, meta in rows]
    logger.info("  已加载 %d 个节点", len(nodes))

    test_query = TEST_QUERIES[0]

    _section("测试查询: %s" % test_query)

    # 1a. 纯语义检索
    _section("1a. 纯语义检索 (pgvector)")
    vector_ret = create_vector_retriever(index, similarity_top_k=5)
    vector_results = vector_ret.retrieve(QueryBundle(query_str=test_query))
    for i, node in enumerate(vector_results):
        _node_block(i, node.score or 0, node.get_content())

    # 1b. 纯 BM25 检索
    _section("1b. 纯 BM25 检索")
    bm25_ret = create_bm25_retriever(nodes, similarity_top_k=5)
    bm25_results = bm25_ret.retrieve(QueryBundle(query_str=test_query))
    for i, node in enumerate(bm25_results):
        _node_block(i, node.score or 0, node.get_content())

    # 1c. 混合检索
    _section("1c. 混合检索 (语义 + BM25 融合)")
    hybrid_ret = create_hybrid_retriever(index, nodes, similarity_top_k=10)
    hybrid_results = hybrid_ret.retrieve(QueryBundle(query_str=test_query))
    for i, node in enumerate(hybrid_results):
        _node_block(i, node.score or 0, node.get_content())


def test_step2_reranker():
    """Step 2: 重排序"""
    _banner("STEP 2: 重排序 (CrossEncoder)")

    from rag.retrieval.rerankers import get_reranker
    from rag.retrieval.retrievers import create_hybrid_retriever
    from rag.ingestion.index_builder import load_index
    from llama_index.core.schema import QueryBundle, TextNode
    import psycopg2

    # 加载
    index = load_index()
    if index is None:
        logger.error("❌ 索引未找到")
        return

    conn = psycopg2.connect(
        host="localhost", port=5432,
        database="medlab_db",
        user="medlab_user", password="medlab_password"
    )
    cur = conn.cursor()
    cur.execute("SELECT node_id, text, metadata_ FROM data_knowledge_vectors")
    rows = cur.fetchall()
    conn.close()
    nodes = [TextNode(id_=nid, text=txt, metadata=meta or {}) for nid, txt, meta in rows]

    test_query = TEST_QUERIES[0]

    _section("查询: %s" % test_query)

    # 召回
    hybrid_ret = create_hybrid_retriever(index, nodes, similarity_top_k=20)
    candidates = hybrid_ret.retrieve(QueryBundle(query_str=test_query))
    logger.info("  混合检索召回: %d 条", len(candidates))

    # 重排序
    reranker = get_reranker()
    if not reranker.is_available:
        logger.error("❌ 重排序器不可用")
        return

    logger.info("  重排序模型: %s", type(reranker._model).__name__)

    # 重排序前
    _section("重排序前 (前 5 条)")
    for i, node in enumerate(candidates[:5]):
        _node_block(i, node.score or 0, node.get_content())

    # 重排序后
    reranked = reranker.rerank(test_query, candidates, top_k=5)
    _section("重排序后 (top 5)")
    for i, node in enumerate(reranked):
        _node_block(i, node.score or 0, node.get_content())


def main():
    _banner("RAG 检索流水线测试", char="█")
    test_step1_retrieval()
    test_step2_reranker()
    _banner("测试完成", char="█")


if __name__ == "__main__":
    main()
