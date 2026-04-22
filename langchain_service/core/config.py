from typing import Optional
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen3-vl-32b-thinking"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    USE_MOCK_LLM: bool = False  # 如果设为 True，使用 Mock LLM 而不真实调用 API

    # ========== 数据库配�?(支持 Docker 内部网络) ==========
    DATABASE_URL: str = "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"
    SQLALCHEMY_DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db")

    VECTOR_DB_TYPE: str = "faiss"
    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", 
                                    "/app/knowledge/vector_db" if os.getenv("DOCKER_ENV") == "true" 
                                    else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge", "vector_db"))

    # ========== Redis 缓存配置 (RAG 知识库缓�? ==========
    REDIS_HOST: str = os.getenv("REDIS_HOST", 
                                "redis" if os.getenv("DOCKER_ENV") == "true" 
                                else "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    RAG_CACHE_TTL_SECONDS: int = 86400  # 24 小时

    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 100

    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000

    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000

    # ========== 服务间通信 (支持 Docker 容器网络和本地开�? ==========
    # �?Docker 中使用容器名称，本地开发使�?localhost
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL",
                                     "http://python-ocr:8001" if os.getenv("DOCKER_ENV") == "true"
                                     else "http://localhost:8001")
    GRAPH_SERVICE_URL: str = os.getenv("GRAPH_SERVICE_URL",
                                       "http://python-langchain:8000" if os.getenv("DOCKER_ENV") == "true"
                                       else "http://localhost:8000")
    OCR_SERVICE_TIMEOUT: float = 60.0
    GRAPH_RETRIEVAL_ENABLED: bool = True
    GRAPH_RETRIEVAL_TOP_EDGES: int = 8

    BACKEND_URL: str = os.getenv("BACKEND_URL",
                                 "http://java-backend:8080" if os.getenv("DOCKER_ENV") == "true"
                                 else "http://localhost:8080")

    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "medlab-agent"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_TRACING_V2: bool = False

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env",
        ),
        extra="ignore",
    )


settings = Settings()
