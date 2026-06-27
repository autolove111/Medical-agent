"""
Medical-agent FastAPI 服务入口

启动方式�?
    conda activate medagent
    cd Medical-agent/python_service
    python server.py

访问�?
    http://localhost:8000/docs     �?Swagger 文档
    http://localhost:8000/redoc    �?ReDoc 文档
    http://localhost:8000/api/user/health �?健康检�?
"""

from __future__ import annotations
import logging
import sys
import os

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 确保 python_service/ �?sys.path 中（支持跨目录运行）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

load_dotenv(os.path.join(_BASE_DIR, ".env"))

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("server")

# 降低 transformers 日志噪音
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

# ---- FastAPI 应用 ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动
    try:
        from app.persistence.database import init_db
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database init skipped: %s", e)

    # 启动短期记忆监控服务
    try:
        from Debugging.short_memory_watching import start_monitor_server
        start_monitor_server(port=8002)
        logger.info("Memory monitor: http://localhost:8002")
    except Exception as e:
        logger.warning("Memory monitor start skipped: %s", e)

    logger.info("=" * 50)
    logger.info("Medical-agent API starting on http://%s:%s",
                 os.getenv("SERVICE_HOST", "0.0.0.0"),
                 os.getenv("SERVICE_PORT", "8000"))
    logger.info("API docs: http://localhost:%s/docs", os.getenv("SERVICE_PORT", "8000"))
    logger.info("Memory monitor: http://localhost:8002")
    logger.info("OCR engine: %s", os.getenv("OCR_ENGINE", "mineru_api"))
    logger.info("OCR service: %s", os.getenv("OCR_SERVICE_URL", "http://localhost:8001"))
    logger.info("AgentLoop: enabled (max 5 steps)")
    logger.info("LLM model will be loaded on first request (lazy)")
    logger.info("=" * 50)
    yield
    # 关闭
    logger.info("Medical-agent API shutting down")


app = FastAPI(
    title="Medical-agent API",
    description="医疗检验报告解读智能助�?�?基于自研 Harness 架构",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8888",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 注册路由 ----

from api.routes.chat import router as chat_router
from api.routes.report import router as report_router
from api.routes.auth import router as auth_router

app.include_router(chat_router)
app.include_router(report_router)
app.include_router(auth_router)


# ---- 根路�?----

@app.get("/")
async def root():
    return {
        "service": "Medical-agent API",
        "version": "0.2.0",
        "docs": "/docs",
        "endpoints": {
            "chat_react_stream": "/api/chat/react-stream",
            "report_upload": "/api/report/upload",
        },
    }


# ---- 入口 ----

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("SERVICE_PORT", "8000"))

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=False,         # 模型在内存中，reload 会导致多次加�?
        log_level="info",
    )
