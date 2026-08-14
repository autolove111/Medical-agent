"""
RAG 摄入流水线测试（步骤 1-3）

测试步骤：
  Step 1: 文档转换 + 清洗（docs/ → to_md/）
  Step 2: 分块（to_md/ → nodes）
  Step 3: 向量化入库（nodes → PostgreSQL）

使用方式：
    cd ai-services
    python -m rag.tests.test_ingestion
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("test_ingestion")


def test_step1_conversion():
    """Step 1: 文档转换 + 清洗"""
    logger.info("=" * 60)
    logger.info("STEP 1: 文档转换 + 清洗 (docs/ → to_md/)")
    logger.info("=" * 60)

    from rag.config import DOCS_DIR, TO_MD_DIR
    from rag.ingestion.cleaners import convert_and_clean

    # 检查源文件
    from pathlib import Path
    source_files = list(DOCS_DIR.rglob("*"))
    source_files = [f for f in source_files if f.is_file()]
    logger.info("源文件目录: %s", DOCS_DIR)
    logger.info("源文件数量: %d", len(source_files))
    for f in source_files:
        logger.info("  %s (%.1f MB)", f.name, f.stat().st_size / 1024 / 1024)

    # 执行转换 + 清洗
    docs = convert_and_clean(force=True)

    # 检查输出
    output_files = list(TO_MD_DIR.glob("*.md"))
    logger.info("-" * 40)
    logger.info("输出目录: %s", TO_MD_DIR)
    logger.info("输出文件数量: %d", len(output_files))
    for f in output_files:
        size = f.stat().st_size
        logger.info("  %s (%.1f KB)", f.name, size / 1024)

    # 内容预览
    if output_files:
        content = output_files[0].read_text(encoding="utf-8")
        lines = content.split("\n")
        logger.info("-" * 40)
        logger.info("内容统计:")
        logger.info("  总行数: %d", len(lines))
        logger.info("  总字符数: %d", len(content))

        # 标题统计
        headings = [l for l in lines if l.strip().startswith("#")]
        logger.info("  标题数量: %d", len(headings))
        for h in headings[:10]:
            logger.info("    %s", h.strip())
        if len(headings) > 10:
            logger.info("    ... 还有 %d 个标题", len(headings) - 10)

        # 检查清洗效果
        logger.info("-" * 40)
        logger.info("清洗效果检查:")
        br_count = content.count("<br>")
        sup_count = content.count("<sup>")
        logger.info("  <br> 残留: %d 处", br_count)
        logger.info("  <sup> 残留: %d 处", sup_count)

    logger.info("")
    return docs


def test_step2_chunking(documents=None):
    """Step 2: 分块"""
    logger.info("=" * 60)
    logger.info("STEP 2: 标题感知分块")
    logger.info("=" * 60)

    from rag.ingestion.loaders import load_all_documents
    from rag.ingestion.chunkers import chunk_documents, save_nodes_to_files

    # 加载文档
    if documents is None:
        documents = load_all_documents()
    logger.info("加载文档数: %d", len(documents))
    for doc in documents:
        logger.info("  %s (%d 字符)", doc.metadata.get("file_name", "?"), len(doc.text or ""))

    # 分块
    nodes = chunk_documents(documents)
    logger.info("-" * 40)
    logger.info("分块结果:")
    logger.info("  总节点数: %d", len(nodes))

    # 统计
    lengths = [len(n.get_content()) for n in nodes]
    logger.info("  平均长度: %.0f 字符", sum(lengths) / len(lengths) if lengths else 0)
    logger.info("  最短长度: %d 字符", min(lengths) if lengths else 0)
    logger.info("  最长长度: %d 字符", max(lengths) if lengths else 0)

    # 标题统计
    headings = [n.metadata.get("heading", "") for n in nodes]
    unique_headings = set(h for h in headings if h)
    logger.info("  不同标题数: %d", len(unique_headings))

    # 预览前 10 个 node
    logger.info("-" * 40)
    logger.info("前 10 个 node 预览:")
    for i, node in enumerate(nodes[:10]):
        heading = node.metadata.get("heading", "")
        text = node.get_content()[:100].replace("\n", "↵")
        logger.info("  [Node #%d] heading=%s | len=%d", i, heading, len(node.get_content()))
        logger.info("    内容: %s", text)

    # 保存到 node_md/
    save_nodes_to_files(documents)
    logger.info("-" * 40)
    logger.info("已保存到 node_md/ 目录")

    logger.info("")
    return nodes


def test_step3_vectorization():
    """Step 3: 向量化入库"""
    logger.info("=" * 60)
    logger.info("STEP 3: 向量化入库 (nodes → PostgreSQL)")
    logger.info("=" * 60)

    import psycopg2

    # 检查 PostgreSQL 连接
    try:
        conn = psycopg2.connect(
            host="localhost", port=5432,
            database="medlab_db",
            user="medlab_user", password="medlab_password"
        )
        cur = conn.cursor()
        logger.info("PostgreSQL 连接成功")
    except Exception as exc:
        logger.error("PostgreSQL 连接失败: %s", exc)
        return

    # 检查 pgvector 扩展
    cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
    result = cur.fetchone()
    if result:
        logger.info("pgvector 扩展: %s v%s", result[0], result[1])
    else:
        logger.error("pgvector 扩展未安装!")
        conn.close()
        return

    # 检查向量表
    cur.execute("SELECT count(*) FROM data_knowledge_vectors")
    count = cur.fetchone()[0]
    logger.info("-" * 40)
    logger.info("向量表: data_knowledge_vectors")
    logger.info("  当前行数: %d", count)

    # 检查表结构
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'data_knowledge_vectors'
        ORDER BY ordinal_position
    """)
    columns = cur.fetchall()
    logger.info("  表结构:")
    for col_name, col_type in columns:
        logger.info("    %s: %s", col_name, col_type)

    # 检查索引
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'data_knowledge_vectors'
    """)
    indexes = cur.fetchall()
    logger.info("  索引:")
    for idx_name, idx_def in indexes:
        logger.info("    %s", idx_name)

    # 预览几条数据
    if count > 0:
        logger.info("-" * 40)
        logger.info("数据预览 (前 3 条):")
        cur.execute("SELECT node_id, text, embedding FROM data_knowledge_vectors LIMIT 3")
        rows = cur.fetchall()
        for node_id, text, embedding in rows:
            text_preview = (text or "")[:80].replace("\n", "↵")
            emb_str = str(embedding)[:50] + "..." if embedding else "None"
            logger.info("  node_id=%s", node_id)
            logger.info("    text: %s", text_preview)
            logger.info("    embedding: %s", emb_str)

    conn.close()
    logger.info("")


def main():
    logger.info("RAG 摄入流水线测试")
    logger.info("")

    # Step 1
    docs = test_step1_conversion()

    # Step 2
    test_step2_chunking(docs)

    # Step 3
    test_step3_vectorization()

    logger.info("=" * 60)
    logger.info("测试完成!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
