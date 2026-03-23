from typing import Optional
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DASHSCOPE_API_KEY: str
    DASHSCOPE_MODEL: str = "qwen3.5-plus-2026-02-15"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    DATABASE_URL: str = "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"

    VECTOR_DB_TYPE: str = "faiss"
    VECTOR_DB_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vector_db")

    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 100

    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000

    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000

    OCR_SERVICE_URL: str = "http://localhost:8001"
    OCR_SERVICE_TIMEOUT: float = 60.0

    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "medlab-agent"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    BACKEND_URL: str = "http://localhost:8080"

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env",
        ),
        extra="ignore",
    )


settings = Settings()
