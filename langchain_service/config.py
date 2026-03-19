from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # AI 配置
    DASHSCOPE_API_KEY: str
    DASHSCOPE_MODEL: str = "qwen3.5-plus-2026-02-15"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"
    
    # 向量库配置
    VECTOR_DB_TYPE: str = "faiss"
    VECTOR_DB_PATH: str = "./vector_db"
    
    # RAG 配置
    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 100
    
    # LangChain 配置
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000
    
    # 服务配置
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000

    # LangSmith 配置（用于生产监控和调试）
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "medlab-agent"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"  
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略 .env 中的额外字段


settings = Settings()
