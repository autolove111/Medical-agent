"""
索引构建器（PostgreSQL + pgvector 版）

从 to_md/ 加载已清洗的文档 → 分块 → 构建 LlamaIndex VectorStoreIndex → 存入 PostgreSQL。
向量存储在 PostgreSQL 的 medlab_db 数据库中（pgvector 扩展）。

表结构：
    llama_index_vector_store_{table_name}
    - id          主键
    - node_id     节点 ID
    - text        原文
    - metadata_   JSON 元数据
    - embedding   vector(768) 向量
"""

import logging
from typing import Optional

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
)
from llama_index.vector_stores.postgres import PGVectorStore

from rag.config import create_embed_model
from rag.ingestion.loaders import load_all_documents
from rag.ingestion.chunkers import chunk_documents

logger = logging.getLogger(__name__)

# PostgreSQL 连接配置
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "medlab_db"
PG_USER = "medlab_user"
PG_PASS = "medlab_password"

# 向量表名（PGVectorStore 会自动加 data_ 前缀，实际表名 = data_knowledge_vectors）
TABLE_NAME = "knowledge_vectors"

# Embedding 维度
EMBED_DIM = 768


def _get_pg_vector_store(
    table_name: str = TABLE_NAME,
    embed_dim: int = EMBED_DIM,
) -> PGVectorStore:
    """创建 PostgreSQL 向量存储实例。"""
    return PGVectorStore.from_params(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASS,
        table_name=table_name,
        embed_dim=embed_dim,
        hybrid_search=True,       # 启用混合搜索（向量 + 全文）
        text_search_config="chinese",  # 中文全文搜索配置
        perform_setup=True,       # 自动建表和索引
    )


def _clear_vector_table(table_name: str) -> None:
    """清空向量表中的所有数据（重建索引前调用）。

    PGVectorStore 会自动在 table_name 前加 'data_' 前缀，
    所以实际的 PostgreSQL 表名是 'data_' + table_name。
    """
    import psycopg2

    actual_table = f"data_{table_name}"

    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        database=PG_DB, user=PG_USER, password=PG_PASS,
    )
    cur = conn.cursor()

    # 检查表是否存在
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (actual_table,))
    table_exists = cur.fetchone()[0]

    if table_exists:
        cur.execute(f"TRUNCATE TABLE {actual_table}")
        conn.commit()
        logger.info("Cleared vector table: %s", actual_table)
    else:
        logger.info("Table %s does not exist yet, will be created", actual_table)

    conn.close()


def build_index(
    documents=None,
    nodes=None,
    table_name: str = TABLE_NAME,
    embed_dim: int = EMBED_DIM,
    clear_existing: bool = True,
) -> VectorStoreIndex:
    """构建向量索引并存入 PostgreSQL。

    流程：清空旧数据 → 加载文档/节点 → 构建索引 → 存入 PostgreSQL。

    两种模式：
      - 传入 documents：先分块再构建索引
      - 传入 nodes：直接构建索引（已分块）

    Args:
        documents: LlamaIndex Document 列表（会自动分块）。为 None 时从 to_md/ 加载。
        nodes: 已分块的 TextNode 列表（跳过分块）。优先级高于 documents。
        table_name: PostgreSQL 中的表名
        embed_dim: Embedding 向量维度
        clear_existing: 是否清空已有数据（默认 True，避免重复）

    Returns:
        构建好的 VectorStoreIndex 实例。
    """
    # 0. 清空已有数据
    if clear_existing:
        _clear_vector_table(table_name)

    # 1. 获取节点
    if nodes is None:
        if documents is None:
            documents = load_all_documents()
        if not documents:
            raise ValueError("No documents to build index from")
        nodes = chunk_documents(documents)
        if not nodes:
            raise ValueError("No nodes generated after chunking")

    # 2. 创建 PostgreSQL 向量存储
    vector_store = _get_pg_vector_store(table_name, embed_dim)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 3. 构建索引（自动调用 embed_model 对每个 node 做 embedding）
    embed_model = create_embed_model()
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )

    logger.info(
        "Index built and stored in PostgreSQL | nodes=%d table=%s",
        len(nodes),
        table_name,
    )
    return index


def load_index(
    table_name: str = TABLE_NAME,
    embed_dim: int = EMBED_DIM,
) -> Optional[VectorStoreIndex]:
    """从 PostgreSQL 加载已构建的索引。

    Returns:
        VectorStoreIndex 实例，或 None（表不存在/加载失败）。
    """
    try:
        vector_store = _get_pg_vector_store(table_name, embed_dim)

        embed_model = create_embed_model()
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=embed_model,
        )
        logger.info("Loaded index from PostgreSQL | table=%s", table_name)
        return index
    except Exception as exc:
        logger.error("Failed to load index from PostgreSQL: %s", exc)
        return None
