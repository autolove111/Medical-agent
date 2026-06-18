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

    logger.info("=" * 50)
    logger.info("Medical-agent API starting on http://%s:%s",
                 os.getenv("SERVICE_HOST", "0.0.0.0"),
                 os.getenv("SERVICE_PORT", "8000"))
    logger.info("API docs: http://localhost:%s/docs", os.getenv("SERVICE_PORT", "8000"))
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
from api.routes.user import router as user_router
from api.routes.auth import router as auth_router

app.include_router(chat_router)
app.include_router(report_router)
app.include_router(user_router)
app.include_router(auth_router)


# ---- 根路�?----

@app.get("/")
async def root():
    return {
        "service": "Medical-agent API",
        "version": "0.2.0",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/chat",
            "chat_stream": "/api/chat/stream",
            "report_upload": "/api/report/upload",
            "user_profile": "/api/user/profile",
            "health": "/api/user/health",
        },
    }

# 兼容旧前端健康检�? GET /api/v1/health
@app.get("/api/v1/health")
async def health_v1():
    return {"status": "UP", "service": "python_service"}

# 兼容旧前端聊天接口（转发到新端点同样逻辑�?
from api.models import ChatRequest

@app.post("/api/v1/agent/chat/stream")
async def chat_stream_v1(
    userQuery: str = "",
    userId: str = "default",
):
    """兼容旧前端流式聊�?POST /api/v1/agent/chat/stream"""
    from fastapi.responses import StreamingResponse
    from api.routes.chat import router as chat_router

    # 直接导入 chat 模块的流式逻辑（简化复用）
    import json, asyncio
    from api.dependencies import get_agent_pool
    from concurrent.futures import ThreadPoolExecutor

    pool = get_agent_pool()
    agent = pool.get_or_create(userId)
    message = userQuery

    async def gen():
        executor = ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        q: asyncio.Queue = asyncio.Queue()

        def _produce():
            try:
                for chunk in agent.chat_stream(message):
                    q.put_nowait(("chunk", chunk.content))
                q.put_nowait(("done", None))
            except Exception as e:
                q.put_nowait(("error", str(e)))

        loop.run_in_executor(executor, _produce)

        while True:
            try:
                kind, payload = await asyncio.wait_for(q.get(), timeout=120.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
                break
            if kind == "done":
                yield f"data: [DONE]\n\n"
                break
            elif kind == "error":
                yield f"data: {json.dumps({'error': payload})}\n\n"
                break
            else:
                yield f"data: {json.dumps({'content': payload})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


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
