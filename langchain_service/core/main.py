import json
import logging
import os
import sys
from pathlib import Path

# 【关键】只添加项目根目录到 sys.path，保持包结构完整
_root_dir = Path(__file__).parent.parent  # /app (langchain_service)
sys.path.insert(0, str(_root_dir))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from core.agent_streaming import create_medical_agent
from core.config import settings
from lab_data_standardization.lab_normalization import extract_lab_results

# 配置 LangSmith/LangChain 追踪（默认关闭，避免无 key 时刷 401）
_tracing_enabled = bool(settings.LANGCHAIN_TRACING_V2 and settings.LANGSMITH_API_KEY)
os.environ["LANGCHAIN_TRACING_V2"] = "true" if _tracing_enabled else "false"
os.environ["LANGSMITH_TRACING"] = "true" if _tracing_enabled else "false"

if _tracing_enabled:
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY or ""
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedLabAgent LangChain 服务",
    description="支持 RAG 和多工具调用的医学 AI Agent",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    user_context: Optional[str] = None
    history: Optional[List[Dict]] = None
    ocr_result: Optional[Dict] = None  # 接收 Java 后端的 OCR 识别结果

class ChatResponse(BaseModel):
    content: str
    sources: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None

@app.get("/health")
async def health():
    return {"status": "UP", "service": "MedLabAgent"}

# --- 核心路由：流式聊天接口 ---

@app.post("/api/v1/agent/chat/stream")
async def chat(
    request: Optional[ChatRequest] = None, 
    userQuery: Optional[str] = Query(None),  # 允许从 URL 参数读取 userQuery
    userId: Optional[str] = Query(None)      # 接收 Java 传来的 userId 查询参数
):
    try:
        # 导入 vision_analyzer 模块用于设置 OCR 缓存
        try:
            from vision.vision_analyzer import set_ocr_result
        except ImportError:
            logger.warning("vision_analyzer module not found, OCR features might be disabled")
            set_ocr_result = lambda x: None
        
        query_text = userQuery
        user_id = userId  # 优先取 URL 参数中的 userId
        user_context = None
        ocr_result = None
        lab_results = {}
        
        if request:
            query_text = query_text or request.query
            user_id = user_id or request.user_id
            user_context = request.user_context
            ocr_result = request.ocr_result  # 从请求体中提取 OCR 结果
            lab_results = _extract_lab_results(ocr_result)

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f">>> 收到 Java 请求: {query_text}，userId: {user_id}")
        
        # 如果接收到 OCR 结果，设置到缓存中
        if ocr_result:
            logger.info("接收到 OCR 识别结果，设置到缓存")
            set_ocr_result(ocr_result)
        if lab_results:
            logger.info("解析到结构化检验值 %s 项", len(lab_results))
        
        agent = create_medical_agent(user_id)

        def event_stream():
            sse_chunk_count = 0
            for event in agent.stream_query(
                query=query_text,
                user_context=user_context,
                lab_results=lab_results if lab_results else None,
            ):
                event_type = event.get("type")
                if event_type == "delta":
                    sse_chunk_count += 1
                    payload = json.dumps(
                        {"content": event.get("content", "")},
                        ensure_ascii=False,
                    )
                    yield f"data: {payload}\n\n"
                elif event_type == "meta":
                    metadata = dict(event.get("metadata", {}))
                    metadata["user_id"] = user_id
                    metadata["sources"] = event.get("sources", [])
                    logger.info("SSE emit meta for userId=%s", user_id)
                    yield f"data: [META:{json.dumps(metadata, ensure_ascii=False)}]\n\n"
                elif event_type == "error":
                    payload = json.dumps(
                        {"error": event.get("error", "Unknown streaming error")},
                        ensure_ascii=False,
                    )
                    logger.error("SSE emit error: %s", payload)
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            logger.info("SSE stream finished for userId=%s", user_id)
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/agent/chat", response_model=ChatResponse)
async def chat_sync(
    request: Optional[ChatRequest] = None, 
    userQuery: Optional[str] = Query(None),
    userId: Optional[str] = Query(None)
):
    """同步聊天接口"""
    try:
        query_text = userQuery
        user_id = userId
        user_context = None
        ocr_result = None
        lab_results = {}
        
        if request:
            query_text = query_text or request.query
            user_id = user_id or request.user_id
            user_context = request.user_context
            ocr_result = request.ocr_result
            lab_results = _extract_lab_results(ocr_result)

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f">>> 收到 Java 同步请求: {query_text}，userId: {user_id}")

        if ocr_result:
            try:
                from vision.vision_analyzer import set_ocr_result
                set_ocr_result(ocr_result)
            except Exception as exc:
                logger.warning("同步接口设置 OCR 缓存失败: %s", exc)
        
        agent = create_medical_agent(user_id)
        response, sources = agent.process_query(
            query=query_text,
            user_context=user_context,
            lab_results=lab_results if lab_results else None,
        )
        
        formatted_sources = [{"content": s.page_content[:200], "metadata": getattr(s, 'metadata', {})} for s in sources] if sources else []
        
        return ChatResponse(
            content=response,
            sources=formatted_sources,
            metadata={"user_id": user_id}
        )
    except Exception as e:
        logger.error(f"同步聊天处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "MedLabAgent LangChain 服务已启动", "docs": "/docs"}

# --- 尝试注册 Graph 路由 ---
try:
    from graph.graph_inference import register_graph_routes
    register_graph_routes(app)
    logger.info("Graph inference routes registered successfully")
except Exception as e:
    logger.warning(f"Failed to register graph inference routes: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )