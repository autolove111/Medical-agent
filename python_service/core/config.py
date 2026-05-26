import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    LLM_MODEL_PATH: str = os.getenv(
        "LLM_MODEL_PATH",
        str(PROJECT_DIR / "models" / "Qwen2.5-7B-Instruct"),
    )
    LLM_USE_4BIT: bool = os.getenv("LLM_USE_4BIT", "true").lower() == "true"
    LLM_4BIT_QUANT_TYPE: str = os.getenv("LLM_4BIT_QUANT_TYPE", "nf4")
    LLM_4BIT_USE_DOUBLE_QUANT: bool = (
        os.getenv("LLM_4BIT_USE_DOUBLE_QUANT", "true").lower() == "true"
    )
    USE_MOCK_LLM: bool = False

    DATABASE_URL: str = "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"
    SQLALCHEMY_DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db",
    )

    VECTOR_DB_TYPE: str = "faiss"
    VECTOR_DB_PATH: str = str(
        (BASE_DIR / os.getenv("VECTOR_DB_PATH", "knowledge/vector_db")).resolve()
    )

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    RAG_CACHE_TTL_SECONDS: int = 86400

    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 100

    RAG_USE_LOCAL_EMBEDDING: bool = os.getenv("RAG_USE_LOCAL_EMBEDDING", "true").lower() == "true"
    RAG_LOCAL_EMBEDDING_PATH: str = os.getenv(
        "RAG_LOCAL_EMBEDDING_PATH",
        str(PROJECT_DIR / "models" / "bce-embedding-base_v1"),
    )
    RAG_EMBEDDING_DEVICE: str = os.getenv("RAG_EMBEDDING_DEVICE", "cpu")

    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000

    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000

    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL", "http://localhost:8001")
    GRAPH_SERVICE_URL: str = os.getenv("GRAPH_SERVICE_URL", "http://localhost:8000")
    OCR_SERVICE_TIMEOUT: float = 60.0
    GRAPH_RETRIEVAL_ENABLED: bool = True
    GRAPH_RETRIEVAL_TOP_EDGES: int = 8

    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8080")

    LANGCHAIN_TRACING_V2: bool = False

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
