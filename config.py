from typing import Optional
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DASHSCOPE_API_KEY: str
    DASHSCOPE_MODEL: str = "qwen3.5-plus-2026-02-15"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ========== 鏁版嵁搴撻厤缃?(鏀寔 Docker 鍐呴儴缃戠粶) ==========
    DATABASE_URL: str = "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"
    SQLALCHEMY_DATABASE_URL: str = "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db"

    VECTOR_DB_TYPE: str = "faiss"
    # 浣跨敤鐜鍙橀噺 VECTOR_DB_PATH锛岄粯璁や负 /app/vector_db锛圖ocker 瀹瑰櫒璺緞锛?    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", 
                                    "/app/vector_db" if os.getenv("DOCKER_ENV") == "true" 
                                    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "vector_db"))

    # ========== Redis 缂撳瓨閰嶇疆 (RAG 鐭ヨ瘑搴撶紦瀛? ==========
    # 鏀寔 Docker 鍐呴儴缃戠粶鍜屾湰鍦板紑鍙?    REDIS_HOST: str = os.getenv("REDIS_HOST", 
                                "redis" if os.getenv("DOCKER_ENV") == "true" 
                                else "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    RAG_CACHE_TTL_SECONDS: int = 86400  # 24 灏忔椂

    RAG_TOP_K: int = 3
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 100

    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000

    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8000

    # ========== 鏈嶅姟闂撮€氫俊 (鏀寔 Docker 瀹瑰櫒缃戠粶鍜屾湰鍦板紑鍙? ==========
    # 鍦?Docker 涓娇鐢ㄥ鍣ㄥ悕绉帮紝鏈湴寮€鍙戜娇鐢?localhost
    OCR_SERVICE_URL: str = os.getenv("OCR_SERVICE_URL",
                                     "http://python-ocr:8001" if os.getenv("DOCKER_ENV") == "true"
                                     else "http://localhost:8001")
    OCR_SERVICE_TIMEOUT: float = 60.0

    BACKEND_URL: str = os.getenv("BACKEND_URL",
                                 "http://java-backend:8080" if os.getenv("DOCKER_ENV") == "true"
                                 else "http://localhost:8080")

    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "medlab-agent"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".env",
        ),
        extra="ignore",
    )


settings = Settings()
