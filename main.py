import json
import logging
import os
import sys
from pathlib import Path

# 銆愬叧閿€戞坊鍔犲叏灞€瀵煎叆璺緞锛岃繖鏍峰瓙鐩綍鐨勬ā鍧楀彲浠ュ郊姝ゅ鍏?
_root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_root_dir / "core"))
sys.path.insert(0, str(_root_dir / "knowledge"))
sys.path.insert(0, str(_root_dir / "graph"))
sys.path.insert(0, str(_root_dir / "task"))
sys.path.insert(0, str(_root_dir / "vision"))
sys.path.insert(0, str(_root_dir / "experimental"))
sys.path.insert(0, str(_root_dir / "utils"))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from agent_streaming import create_medical_agent
from .config import settings
# Configure LangSmith tracing (optional)
os.environ.setdefault("LANGSMITH_TRACING_V2", "true")

# 浠?settings 璇诲彇 LangSmith 閰嶇疆
if settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
if settings.LANGSMITH_PROJECT:
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
if settings.LANGSMITH_ENDPOINT:
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT

# 鏃ュ織閰嶇疆
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedLabAgent LangChain 鏈嶅姟",
    description="鏀寔 RAG 鍜屽宸ュ叿璋冪敤鐨勫尰瀛?AI Agent",
    version="1.0.0"
)

# CORS 閰嶇疆
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
    ocr_result: Optional[Dict] = None  # 銆愭柟妗?B銆戞帴鏀?Java 鍚庣鐨?OCR 璇嗗埆缁撴灉

class ChatResponse(BaseModel):
    content: str
    sources: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None

@app.get("/health")
async def health():
    return {"status": "UP", "service": "MedLabAgent"}

# --- 鏍稿績淇锛氭坊鍔?/stream 鍚庣紑浠ュ榻?Java 鍚庣鐨勮姹傝矾寰?---
# ... 鍓嶉潰浠ｇ爜淇濇寔涓嶅彉 ...

@app.post("/api/v1/agent/chat/stream")
async def chat(
    request: Optional[ChatRequest] = None, 
    userQuery: Optional[str] = Query(None),  # 鍏抽敭淇锛氬厑璁镐粠 URL 鍙傛暟璇诲彇 userQuery
    userId: Optional[str] = Query(None)      # 銆愭柊澧炪€戞帴鏀?Java 浼犳潵鐨?userId 鏌ヨ鍙傛暟
):
    try:
        # 銆愭柟妗?B銆戝鍏?vision_analyzer 妯″潡鐢ㄤ簬璁剧疆 OCR 缂撳瓨
        from vision_analyzer import set_ocr_result
        
        query_text = userQuery
        user_id = userId  # 銆愪慨澶嶃€戜紭鍏堝彇 URL 鍙傛暟涓殑 userId
        user_context = None
        ocr_result = None
        
        if request:
            query_text = query_text or request.query
            # 鍙湁 URL 涓病鏈?userId 鏃讹紝鎵嶄粠 request 浣撲腑璇诲彇
            user_id = user_id or request.user_id
            user_context = request.user_context
            ocr_result = request.ocr_result  # 銆愭柟妗?B銆戜粠璇锋眰涓彁鍙?OCR 缁撴灉

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f">>> 鏀跺埌 Java 璇锋眰: {query_text}锛寀serId: {user_id}")
        
        # 銆愭柟妗?B銆戝鏋滄帴鏀跺埌 OCR 缁撴灉锛岃缃埌缂撳瓨涓?
        if ocr_result:
            logger.info("鉁?銆愭柟妗?B銆戞帴鏀跺埌 OCR 璇嗗埆缁撴灉锛岃缃埌缂撳瓨")
            set_ocr_result(ocr_result)
        
        agent = create_medical_agent(user_id)

        def event_stream():
            sse_chunk_count = 0
            for event in agent.stream_query(
                query=query_text,
                user_context=user_context
            ):
                event_type = event.get("type")
                if event_type == "delta":
                    sse_chunk_count += 1
                    payload = json.dumps(
                        {"content": event.get("content", "")},
                        ensure_ascii=False,
                    )
                    logger.info(
                        "SSE emit chunk #%s payloadLen=%s",
                        sse_chunk_count,
                        len(payload),
                    )
                    yield f"data: {payload}\n\n"
                elif event_type == "meta":
                    metadata = dict(event.get("metadata", {}))
                    metadata["user_id"] = user_id
                    metadata["sources"] = event.get("sources", [])
                    logger.info("SSE emit meta for userId=%s chunkCount=%s", user_id, sse_chunk_count)
                    yield f"data: [META:{json.dumps(metadata, ensure_ascii=False)}]\n\n"
                elif event_type == "error":
                    payload = json.dumps(
                        {"error": event.get("error", "Unknown streaming error")},
                        ensure_ascii=False,
                    )
                    logger.error("SSE emit error payload=%s", payload)
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            logger.info("SSE stream finished chunkCount=%s userId=%s", sse_chunk_count, user_id)
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
        
        # 鏍煎紡鍖栨暟鎹簮 (淇濇寔鍘熸牱)
    except Exception as e:
        logger.error(f"澶勭悊澶辫触: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/agent/chat", response_model=ChatResponse)
async def chat_sync(
    request: Optional[ChatRequest] = None, 
    userQuery: Optional[str] = Query(None),
    userId: Optional[str] = Query(None)     # 銆愭柊澧炪€戞帴鏀?Java 浼犳潵鐨?userId 鏌ヨ鍙傛暟
):
    """鍚屾鑱婂ぉ鎺ュ彛 - 渚?Java 鍚庣璋冪敤"""
    try:
        # 鍏煎閫昏緫锛氫紭鍏堝彇 URL 閲岀殑鍙傛暟锛屽鏋滄病鏈夊垯鍙?JSON 浣撻噷鐨勬暟鎹?
        query_text = userQuery
        user_id = userId  # 銆愪慨澶嶃€戜紭鍏堝彇 URL 鍙傛暟涓殑 userId
        user_context = None
        history = None
        
        if request:
            query_text = query_text or request.query
            user_id = user_id or request.user_id
            user_context = request.user_context
            history = request.history

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f">>> 鏀跺埌 Java 鍚屾鑱婂ぉ璇锋眰: {query_text}锛寀serId: {user_id}")
        
        agent = create_medical_agent(user_id)
        response, sources = agent.process_query(
            query=query_text,
            user_context=user_context
        )
        
        # 鏍煎紡鍖栨暟鎹簮
        formatted_sources = [{"content": s.page_content[:200], "metadata": getattr(s, 'metadata', {})} for s in sources] if sources else []
        
        return ChatResponse(
            content=response,
            sources=formatted_sources,
            metadata={"user_id": user_id}
        )
    except Exception as e:
        logger.error(f"鍚屾鑱婂ぉ澶勭悊澶辫触: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "MedLabAgent LangChain 鏈嶅姟宸插惎鍔?, "docs": "/docs"}

# ============================================
# 鍙屽浘鏋舵瀯闆嗘垚锛圥hase 1: 鐭ヨ瘑鍥捐氨涓?GAT锛?
# ============================================
try:
    from graph_inference import register_graph_routes
    register_graph_routes(app)
    logger.info("鉁?Graph inference routes registered successfully")
except Exception as e:
    logger.warning(f"鈿狅笍 Failed to register graph inference routes: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
