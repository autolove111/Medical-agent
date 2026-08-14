"""
LlamaIndex RAG 全局配置

统一管理 embedding 模型、分块参数、检索参数等。
在项目启动时 import 一次，后续所有模块共用。
"""

import os
import logging
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 路径常量
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DATA_DIR = PROJECT_ROOT / "memory" / "knowledge"
DOCS_DIR = KNOWLEDGE_DATA_DIR / "docs"
TO_MD_DIR = KNOWLEDGE_DATA_DIR / "to_md"
NODE_MD_DIR = KNOWLEDGE_DATA_DIR / "node_md"

# LlamaIndex 持久化目录
LLAMA_INDEX_DB_DIR = KNOWLEDGE_DATA_DIR / "vector_db" / "llama_index"


# ============================================================
# LlamaIndex Settings 初始化
# ============================================================

def init_llama_settings():
    """初始化 LlamaIndex 全局 Settings（只调一次）。

    必须在创建 Index / QueryEngine 之前调用。
    """
    from llama_index.core import Settings
    from llama_index.core.node_parser import SentenceSplitter

    # Embedding
    embed_model = create_embed_model()
    Settings.embed_model = embed_model

    # 分块
    Settings.node_parser = SentenceSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )

    # 日志级别
    Settings.chunk_size = settings.CHUNK_SIZE
    Settings.chunk_overlap = settings.CHUNK_OVERLAP

    logger.info(
        "LlamaIndex Settings initialized | chunk_size=%d overlap=%d embed=%s",
        settings.CHUNK_SIZE,
        settings.CHUNK_OVERLAP,
        type(embed_model).__name__,
    )
    return Settings


def create_embed_model():
    """创建 Embedding 模型实例（本地 HuggingFace 或 OpenAI 兼容 API）。

    根据 settings.RAG_USE_LOCAL_EMBEDDING 自动切换。
    """
    if not settings.RAG_USE_LOCAL_EMBEDDING:
        from llama_index.embeddings.openai import OpenAIEmbedding
        model = OpenAIEmbedding(
            model_name=settings.RAG_EMBEDDING_MODEL_NAME,
            api_key=settings.RAG_EMBEDDING_API_KEY or None,
            api_base=settings.RAG_EMBEDDING_API_URL or None,
        )
        logger.info("Embedding: OpenAI API | model=%s", settings.RAG_EMBEDDING_MODEL_NAME)
        return model

    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    model_path = settings.RAG_LOCAL_EMBEDDING_PATH
    device = settings.RAG_EMBEDDING_DEVICE

    model = HuggingFaceEmbedding(
        model_name=model_path,
        device=device,
        trust_remote_code=True,
    )
    logger.info("Embedding: HuggingFace local | path=%s device=%s", model_path, device)
    return model


def create_reranker():
    """创建 CrossEncoder 重排序器（延迟加载，首次调用时才加载模型）。

    返回 SentenceTransformerRerank 实例，或 None（模型不可用时）。
    """
    if not settings.RERANKER_ENABLED:
        return None

    try:
        from llama_index.core.postprocessor import SentenceTransformerRerank
        reranker = SentenceTransformerRerank(
            model=settings.RERANKER_MODEL_PATH,
            top_n=settings.RERANKER_FINAL_K,
            device=settings.RERANKER_DEVICE,
        )
        logger.info(
            "Reranker: SentenceTransformerRerank | model=%s top_n=%d",
            settings.RERANKER_MODEL_PATH,
            settings.RERANKER_FINAL_K,
        )
        return reranker
    except Exception as exc:
        logger.warning("Reranker init failed, will skip reranking: %s", exc)
        return None
