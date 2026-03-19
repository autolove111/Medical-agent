import logging
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from agent import create_medical_agent
from config import settings

# Configure LangSmith tracing (optional)
os.environ.setdefault("LANGSMITH_TRACING_V2", "true")

# 从 settings 读取 LangSmith 配置
if settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
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

class ChatResponse(BaseModel):
    content: str
    sources: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None

@app.get("/health")
async def health():
    return {"status": "UP", "service": "MedLabAgent"}

# --- 核心修复：添加 /stream 后缀以对齐 Java 后端的请求路径 ---
# ... 前面代码保持不变 ...

@app.post("/api/v1/agent/chat/stream", response_model=ChatResponse)
async def chat(
    request: Optional[ChatRequest] = None, 
    userQuery: Optional[str] = Query(None),  # 关键修复：允许从 URL 参数读取 userQuery
    userId: Optional[str] = Query(None)      # 【新增】接收 Java 传来的 userId 查询参数
):
    try:
        # 兼容逻辑：优先取 URL 里的参数，如果没有则取 JSON 体里的数据
        query_text = userQuery
        user_id = userId  # 【修复】优先取 URL 参数中的 userId
        user_context = None
        
        if request:
            query_text = query_text or request.query
            # 只有 URL 中没有 userId 时，才从 request 体中读取
            user_id = user_id or request.user_id
            user_context = request.user_context

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f">>> 收到 Java 请求: {query_text}，userId: {user_id}")
        
        agent = create_medical_agent(user_id)
        response, sources = agent.process_query(
            query=query_text,
            user_context=user_context
        )
        
        # 格式化数据源 (保持原样)
        formatted_sources = [{"content": s.page_content[:200], "metadata": getattr(s, 'metadata', {})} for s in sources]
        
        return ChatResponse(
            content=response,
            sources=formatted_sources,
            metadata={"user_id": user_id}
        )
    except Exception as e:
        logger.error(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/agent/chat", response_model=ChatResponse)
async def chat_sync(
    request: Optional[ChatRequest] = None, 
    userQuery: Optional[str] = Query(None),
    userId: Optional[str] = Query(None)     # 【新增】接收 Java 传来的 userId 查询参数
):
    """同步聊天接口 - 供 Java 后端调用"""
    try:
        # 兼容逻辑：优先取 URL 里的参数，如果没有则取 JSON 体里的数据
        query_text = userQuery
        user_id = userId  # 【修复】优先取 URL 参数中的 userId
        user_context = None
        history = None
        
        if request:
            query_text = query_text or request.query
            user_id = user_id or request.user_id
            user_context = request.user_context
            history = request.history

        if not query_text:
            raise HTTPException(status_code=400, detail="Query text is required")

        logger.info(f">>> 收到 Java 同步聊天请求: {query_text}，userId: {user_id}")
        
        agent = create_medical_agent(user_id)
        response, sources = agent.process_query(
            query=query_text,
            user_context=user_context
        )
        
        # 格式化数据源
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )