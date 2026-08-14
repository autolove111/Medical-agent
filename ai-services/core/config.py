"""
AI 服务配置
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env.local", override=True)


class Settings:
    """配置类"""

    # 模型路径
    LLM_MODEL_PATH: str = os.getenv(
        "LLM_MODEL_PATH",
        str(BASE_DIR.parent / "models" / "Qwen2.5-7B-Instruct")
    )

    # RAG 配置
    RAG_USE_LOCAL_EMBEDDING: bool = os.getenv("RAG_USE_LOCAL_EMBEDDING", "true").lower() == "true"
    RAG_LOCAL_EMBEDDING_PATH: str = os.getenv(
        "EMBEDDING_MODEL_PATH",
        str(BASE_DIR.parent / "models" / "bce-embedding-base_v1")
    )
    RAG_EMBEDDING_DEVICE: str = os.getenv("RAG_EMBEDDING_DEVICE", "cuda")
    RAG_EMBEDDING_API_URL: str = os.getenv("RAG_EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings")
    RAG_EMBEDDING_API_KEY: str = os.getenv("RAG_EMBEDDING_API_KEY", "")
    RAG_EMBEDDING_MODEL_NAME: str = os.getenv("RAG_EMBEDDING_MODEL_NAME", "text-embedding-3-small")
    RAG_EMBEDDING_API_TIMEOUT: int = int(os.getenv("RAG_EMBEDDING_API_TIMEOUT", "30"))

    # 向量数据库
    VECTOR_DB_TYPE: str = "faiss"
    VECTOR_DB_PATH: str = str(
        (BASE_DIR / os.getenv("VECTOR_DB_PATH", "harness/memory/knowledge/data/vector_db")).resolve()
    )

    # Reranker 配置
    RERANKER_ENABLED: bool = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
    RERANKER_MODEL_PATH: str = os.getenv(
        "RERANKER_MODEL_PATH",
        str(BASE_DIR.parent / "models" / "bge-reranker-base")
    )
    RERANKER_DEVICE: str = os.getenv("RERANKER_DEVICE", "cpu")
    RERANKER_TOP_K: int = int(os.getenv("RERANKER_TOP_K", "40"))
    RERANKER_FINAL_K: int = int(os.getenv("RERANKER_FINAL_K", "5"))
    RERANKER_SCORE_THRESHOLD: float = float(os.getenv("RERANKER_SCORE_THRESHOLD", "0.1"))

    # RAG 参数
    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # 模型参数
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000


settings = Settings()
