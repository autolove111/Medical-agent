"""
Elasticsearch + IK 医学词典 初始化脚本

功能：
1. 创建 ES 索引（使用 IK 分词器 + 医学自定义词典）
2. 从 PostgreSQL 导入所有文档到 ES
3. 验证搜索功能

用法：
    cd ai-services
    python -m rag.elasticsearch.es_setup
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("es_setup")

# ES 配置
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX = "medical_knowledge"

# PostgreSQL 配置
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "medlab_db"
PG_USER = "medlab_user"
PG_PASS = "medlab_password"


def get_es_client():
    """获取 ES 客户端连接。"""
    from elasticsearch import Elasticsearch

    es = Elasticsearch(ES_HOST)
    # 等待 ES 就绪
    for i in range(30):
        try:
            if es.ping():
                logger.info("Connected to Elasticsearch at %s", ES_HOST)
                return es
        except Exception:
            pass
        logger.info("Waiting for ES... (%d/30)", i + 1)
        time.sleep(2)

    raise ConnectionError(f"Cannot connect to Elasticsearch at {ES_HOST}")


def load_medical_dict() -> list:
    """加载医学自定义词典。"""
    dict_path = Path(__file__).parent / "medical_dict.dic"
    words = []
    with open(dict_path, "r", encoding="utf-8") as f:
        for line in f:
            word = line.strip()
            if word:
                words.append(word)
    logger.info("Loaded %d medical terms from dictionary", len(words))
    return words


def create_index(es):
    """创建 ES 索引，配置 IK 分词器。"""

    # 删除旧索引（如果存在）
    if es.indices.exists(index=ES_INDEX):
        es.indices.delete(index=ES_INDEX)
        logger.info("Deleted existing index: %s", ES_INDEX)

    # 索引配置
    settings = {
        "analysis": {
            "analyzer": {
                "medical_analyzer": {
                    "type": "custom",
                    "tokenizer": "smartcn_tokenizer",
                    "filter": ["lowercase"]
                },
                "medical_search_analyzer": {
                    "type": "custom",
                    "tokenizer": "smartcn_tokenizer",
                    "filter": ["lowercase"]
                }
            }
        }
    }

    mappings = {
        "properties": {
            "node_id": {"type": "keyword"},
            "text": {
                "type": "text",
                "analyzer": "medical_analyzer",
                "search_analyzer": "medical_search_analyzer"
            },
            "heading": {
                "type": "text",
                "analyzer": "medical_analyzer",
                "search_analyzer": "medical_search_analyzer"
            },
            "source": {"type": "keyword"},
            "chunk_id": {"type": "integer"}
        }
    }

    es.indices.create(
        index=ES_INDEX,
        settings=settings,
        mappings=mappings,
    )
    logger.info("Created index: %s with IK medical analyzer", ES_INDEX)


def import_documents(es):
    """从 PostgreSQL 导入文档到 ES。"""
    import psycopg2

    # 从 PostgreSQL 读取所有节点
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        database=PG_DB, user=PG_USER, password=PG_PASS,
    )
    cur = conn.cursor()

    # 查询所有节点（node_id, text, metadata_）
    cur.execute("""
        SELECT node_id, text, metadata_
        FROM data_knowledge_vectors
        ORDER BY CAST(node_id AS INTEGER)
    """)
    rows = cur.fetchall()
    logger.info("Loaded %d documents from PostgreSQL", len(rows))

    # 批量导入 ES
    from elasticsearch.helpers import bulk

    actions = []
    for node_id, text, metadata_json in rows:
        # 解析 metadata
        if isinstance(metadata_json, str):
            metadata = json.loads(metadata_json)
        else:
            metadata = metadata_json or {}

        heading = metadata.get("heading", "")
        source = metadata.get("source", "")

        actions.append({
            "_index": ES_INDEX,
            "_id": node_id,
            "_source": {
                "node_id": str(node_id),
                "text": text or "",
                "heading": heading,
                "source": source,
            }
        })

    # 分批导入（每批 500 条）
    batch_size = 500
    total_imported = 0
    for i in range(0, len(actions), batch_size):
        batch = actions[i:i + batch_size]
        success, errors = bulk(es, batch, raise_on_error=False)
        total_imported += success
        if errors:
            logger.warning("Batch %d: %d errors", i // batch_size, len(errors))

    conn.close()

    # 刷新索引使文档可搜索
    es.indices.refresh(index=ES_INDEX)
    logger.info("Imported %d documents to ES index '%s'", total_imported, ES_INDEX)
    return total_imported


def verify_search(es):
    """验证搜索功能。"""
    test_queries = [
        "IgA肾病的治疗方法",
        "嗜铬细胞瘤",
        "急性心力衰竭",
        "头孢曲松",
    ]

    logger.info("\n=== Search Verification ===")
    for query in test_queries:
        body = {
            "query": {
                "match": {
                    "text": query
                }
            },
            "size": 3,
            "_source": ["node_id", "heading"]
        }
        resp = es.search(index=ES_INDEX, body=body)
        hits = resp["hits"]["hits"]
        logger.info("\nQuery: %s", query)
        for hit in hits:
            logger.info("  #%s  score=%.2f  %s",
                       hit["_source"]["node_id"],
                       hit["_score"],
                       hit["_source"]["heading"][:60])


def main():
    logger.info("=== Elasticsearch + IK Medical Setup ===\n")

    # 1. 连接 ES
    es = get_es_client()

    # 2. 加载医学词典（仅供参考，IK 内置词典已覆盖大部分）
    medical_terms = load_medical_dict()

    # 3. 创建索引
    create_index(es)

    # 4. 导入文档
    total = import_documents(es)

    # 5. 验证搜索
    verify_search(es)

    logger.info("\n=== Setup Complete ===")
    logger.info("Index: %s", ES_INDEX)
    logger.info("Documents: %d", total)
    logger.info("Analyzer: IK (ik_max_word / ik_smart)")


if __name__ == "__main__":
    main()
