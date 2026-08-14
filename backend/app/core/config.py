import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 路径定义
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
ROOT_DIR = PROJECT_DIR.parent  # 项目根目录（dachuang/）

# 加载配置：.env 先加载，.env.local 后加载（覆盖）
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local", override=True)


class Settings(BaseSettings):
    # ========================
    # 数据库
    # ========================
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"
    )

    # ========================
    # Redis
    # ========================
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # ========================
    # 模型路径
    # ========================
    LLM_MODEL_PATH: str = os.getenv(
        "LLM_MODEL_PATH",
        str(PROJECT_DIR / "models" / "Qwen2.5-7B-Instruct")
    )
    LLM_USE_4BIT: bool = os.getenv("LLM_USE_4BIT", "true").lower() == "true"
    LLM_4BIT_QUANT_TYPE: str = os.getenv("LLM_4BIT_QUANT_TYPE", "nf4")
    LLM_4BIT_USE_DOUBLE_QUANT: bool = (
        os.getenv("LLM_4BIT_USE_DOUBLE_QUANT", "true").lower() == "true"
    )
    USE_MOCK_LLM: bool = False

    # ========================
    # RAG 配置
    # ========================
    RAG_USE_LOCAL_EMBEDDING: bool = os.getenv("RAG_USE_LOCAL_EMBEDDING", "true").lower() == "true"
    RAG_LOCAL_EMBEDDING_PATH: str = os.getenv(
        "EMBEDDING_MODEL_PATH",
        str(PROJECT_DIR / "models" / "bce-embedding-base_v1")
    )
    RAG_EMBEDDING_DEVICE: str = os.getenv("RAG_EMBEDDING_DEVICE", "cpu")
    RAG_EMBEDDING_API_URL: str = os.getenv("RAG_EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings")
    RAG_EMBEDDING_API_KEY: str = os.getenv("RAG_EMBEDDING_API_KEY", "")
    RAG_EMBEDDING_MODEL_NAME: str = os.getenv("RAG_EMBEDDING_MODEL_NAME", "text-embedding-3-small")
    RAG_EMBEDDING_API_TIMEOUT: int = int(os.getenv("RAG_EMBEDDING_API_TIMEOUT", "30"))

    # ========================
    # 向量数据库
    # ========================
    VECTOR_DB_TYPE: str = "faiss"
    VECTOR_DB_PATH: str = str(
        (BASE_DIR / os.getenv("VECTOR_DB_PATH", "harness/memory/knowledge/data/vector_db")).resolve()
    )

    # ========================
    # Reranker 配置
    # ========================
    RERANKER_ENABLED: bool = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
    RERANKER_MODEL_PATH: str = os.getenv(
        "RERANKER_MODEL_PATH",
        str(PROJECT_DIR / "models" / "bge-reranker-base")
    )
    RERANKER_DEVICE: str = os.getenv("RERANKER_DEVICE", "cpu")
    RERANKER_TOP_K: int = int(os.getenv("RERANKER_TOP_K", "40"))
    RERANKER_FINAL_K: int = int(os.getenv("RERANKER_FINAL_K", "10"))
    RERANKER_SCORE_THRESHOLD: float = float(os.getenv("RERANKER_SCORE_THRESHOLD", "0.1"))

    # ========================
    # RAG 参数
    # ========================
    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    # ========================
    # 模型参数
    # ========================
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000
    CONTEXT_WINDOW: int = int(os.getenv("CONTEXT_WINDOW", "32768"))
    PROMPT_RATIO: float = float(os.getenv("PROMPT_RATIO", "0.6"))
    OUTPUT_RATIO: float = float(os.getenv("OUTPUT_RATIO", "0.3"))
    BUFFER_RATIO: float = float(os.getenv("BUFFER_RATIO", "0.1"))

    # ========================
    # 服务配置
    # ========================
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000

    # ========================
    # 日志配置
    # ========================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ========================
    # OCR 服务
    # ========================
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://localhost:8001")
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "mineru_api")
    MINERU_API_BASE_URL: str = os.getenv("MINERU_API_BASE_URL", "https://mineru.net")
    MINERU_API_TOKEN: str = os.getenv("MINERU_API_TOKEN", "")
    MINERU_POLL_INTERVAL: float = float(os.getenv("MINERU_POLL_INTERVAL", "3.0"))
    MINERU_POLL_TIMEOUT: float = float(os.getenv("MINERU_POLL_TIMEOUT", "300.0"))

    # ========================
    # 其他服务
    # ========================
    GRAPH_SERVICE_URL: str = os.getenv("GRAPH_SERVICE_URL", "http://localhost:8000")
    OCR_SERVICE_TIMEOUT: float = 60.0
    GRAPH_RETRIEVAL_ENABLED: bool = True
    GRAPH_RETRIEVAL_TOP_EDGES: int = 8
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8080")

    # ========================
    # LangChain
    # ========================
    LANGCHAIN_TRACING_V2: bool = False

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
