"""
Medical-agent FastAPI 统一服务

职责：
  - 网关（认证、报告上传）
  - AI 路由（LLM、RAG、记忆、工具、Agent 循环、WebSocket）

AI 模块在 ai-services/，其余在 backend/app/。

启动方式:
    cd backend
    python server.py
"""

from __future__ import annotations
import os
import sys
import logging
import asyncio

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ============================================================
# 路径设置
# ============================================================

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.join(_BASE_DIR, "app")
_AI_DIR = os.path.join(_BASE_DIR, "..", "ai-services")

for _p in [_APP_DIR, _AI_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ============================================================
# 日志
# ============================================================

from app.core.logging import setup_logging, get_logger
from app.core.config import settings

setup_logging(level=settings.LOG_LEVEL if hasattr(settings, 'LOG_LEVEL') else "INFO")
logger = get_logger("server")

# ============================================================
# 生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 初始化数据库
    try:
        from app.models.database import init_db
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning("数据库初始化跳过: %s", e)

    # 初始化记忆数据库
    try:
        from memory.persistence.database import init_db as init_memory_db
        init_memory_db()
        logger.info("记忆数据库初始化完成")
    except Exception as e:
        logger.warning("记忆数据库初始化跳过: %s", e)

    logger.info("=" * 50)
    logger.info("Medical-agent API 启动中...")
    logger.info("地址: http://%s:%s", settings.SERVICE_HOST, settings.SERVICE_PORT)
    logger.info("API 文档: http://localhost:%s/docs", settings.SERVICE_PORT)
    logger.info("=" * 50)

    # 启动 WebSocket 推送后台任务
    from app.api.routes.ws import push_worker
    push_task = asyncio.create_task(push_worker())

    yield

    # 关闭
    push_task.cancel()
    logger.info("Medical-agent API 已关闭")


# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="Medical-agent API",
    description="医疗检验报告解读智能助手",
    version="0.3.0",
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 注册路由
# ============================================================

# 网关路由
from app.api.routes.auth import router as auth_router
from app.api.routes.report import router as report_router
from app.api.routes.chat import router as chat_router

# AI 路由
from app.api.routes.task import router as task_router
from app.api.routes.ws import router as ws_router
from app.api.routes.llm import router as llm_router
from app.api.routes.rag import router as rag_router
from app.api.routes.memory import router as memory_router
from app.api.routes.tools import router as tools_router
from app.api.routes.ocr import router as ocr_router
app.include_router(auth_router)
app.include_router(report_router)
app.include_router(chat_router)
app.include_router(task_router)
app.include_router(ws_router)
app.include_router(llm_router)
app.include_router(rag_router)
app.include_router(memory_router)
app.include_router(tools_router)
app.include_router(ocr_router)


# ============================================================
# 健康检查
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Medical-agent API",
        "version": "0.3.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=settings.SERVICE_HOST,
        port=settings.SERVICE_PORT,
        reload=False,
        log_level="info",
    )
