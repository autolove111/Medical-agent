import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

_root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(_root_dir))

from agents import AVAILABLE_AGENT_TYPES, create_agent
from lab_data_standardization.lab_normalization import extract_lab_results
from vision.vision_analyzer import set_ocr_result

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def init_headers(self, headers: Optional[Dict[str, str]] = None) -> None:
        super().init_headers(headers)
        self.headers["Content-Type"] = "application/json; charset=utf-8"


app = FastAPI(
    title="MedLabAgent LangChain Service",
    description="Standalone medical agents with shared OCR, shared tools, and shared RAG.",
    version="2.0.0",
    default_response_class=UTF8JSONResponse,
)

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
    history: Optional[List[Dict[str, Any]]] = None
    ocr_result: Optional[Dict[str, Any]] = None
    agent_type: Optional[str] = None


class ChatResponse(BaseModel):
    content: str
    sources: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


@app.get("/health")
async def health():
    return {"status": "UP", "service": "MedLabAgent"}


@app.get("/api/v1/agents")
async def list_agents():
    return {"agents": AVAILABLE_AGENT_TYPES}


def _resolve_request_payload(
    request: Optional[ChatRequest],
    user_query: Optional[str],
    user_id: Optional[str],
    agent_type: Optional[str],
):
    query_text = user_query
    resolved_user_id = user_id
    user_context = None
    ocr_result = None
    lab_results = {}

    if request:
        query_text = query_text or request.query
        resolved_user_id = resolved_user_id or request.user_id
        user_context = request.user_context
        ocr_result = request.ocr_result
        if ocr_result:
            lab_results = extract_lab_results(ocr_result) or {}

    if not query_text:
        raise HTTPException(status_code=400, detail="Query text is required")

    if ocr_result:
        set_ocr_result(ocr_result)

    _ = agent_type
    selected_agent = "general"
    return query_text, resolved_user_id, user_context, lab_results, selected_agent


@app.post("/api/v1/agent/chat/stream")
async def chat(
    request: Optional[ChatRequest] = None,
    userQuery: Optional[str] = Query(None),
    userId: Optional[str] = Query(None),
    agentType: Optional[str] = Query(None),
):
    try:
        query_text, user_id, user_context, lab_results, selected_agent = _resolve_request_payload(
            request,
            userQuery,
            userId,
            agentType,
        )

        logger.info(
            "Streaming request received | agent=%s user_id=%s query=%s",
            selected_agent,
            user_id,
            query_text[:200],
        )

        agent = create_agent(agent_type=selected_agent, user_id=user_id)

        def event_stream():
            for event in agent.stream_query(
                query=query_text,
                user_context=user_context,
                lab_results=lab_results or None,
            ):
                event_type = event.get("type")
                if event_type == "delta":
                    payload = json.dumps({"content": event.get("content", "")}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                elif event_type == "meta":
                    metadata = dict(event.get("metadata", {}))
                    metadata["user_id"] = user_id
                    metadata["agent_type"] = selected_agent
                    metadata["sources"] = event.get("sources", [])
                    yield f"data: [META:{json.dumps(metadata, ensure_ascii=False)}]\n\n"
                elif event_type == "error":
                    payload = json.dumps({"error": event.get("error", "Unknown error")}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
                    return

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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Streaming chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/agent/chat", response_model=ChatResponse)
async def chat_sync(
    request: Optional[ChatRequest] = None,
    userQuery: Optional[str] = Query(None),
    userId: Optional[str] = Query(None),
    agentType: Optional[str] = Query(None),
):
    try:
        query_text, user_id, user_context, lab_results, selected_agent = _resolve_request_payload(
            request,
            userQuery,
            userId,
            agentType,
        )

        logger.info(
            "Sync request received | agent=%s user_id=%s query=%s",
            selected_agent,
            user_id,
            query_text[:200],
        )

        agent = create_agent(agent_type=selected_agent, user_id=user_id)
        response, sources = agent.process_query(
            query=query_text,
            user_context=user_context,
            lab_results=lab_results or None,
        )

        formatted_sources = [
            {"content": source.page_content[:200], "metadata": getattr(source, "metadata", {})}
            for source in (sources or [])
        ]

        response_dict = {
            "content": response,
            "sources": formatted_sources,
            "metadata": {"user_id": user_id, "agent_type": selected_agent},
        }
        return UTF8JSONResponse(content=response_dict)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Sync chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/")
async def root():
    return {
        "message": "MedLabAgent service is running",
        "docs": "/docs",
        "agents": AVAILABLE_AGENT_TYPES,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
