"""
聊天路由：同步对话 + SSE 流式对话

Phase 3 增强：接入 InterpretationEngine 输出结构化解读
- 报告首轮对话自动触发完整解读管线（指标+联动+饮食+运动+来源引用）
- 返回结构化来源元数据（source/ section/ excerpt/ category）
- 后续追问维持会话上下文
"""

from __future__ import annotations
import json
import logging
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.models import ChatRequest, ChatResponse
from api.dependencies import get_agent_pool
from api.routes.report import get_report
from app.business.report_pipeline import get_report_pipeline
from app.business.interpretation_engine import get_interpretation_engine

logger = logging.getLogger(__name__)

_META_PATTERN = re.compile(r"\[META\|([^\]]+)\]")


def extract_metadata(text: str) -> tuple[str, dict]:
    """从AI回复中提取[META|diseases:...|drugAllergies:...]结构化元数据。"""
    metadata = {"isMedical": False, "diseases": "", "drugAllergies": ""}
    match = _META_PATTERN.search(text)
    if not match:
        return text, metadata
    parsed = {}
    for field in match.group(1).split("|"):
        if ":" not in field:
            continue
        k, v = field.split(":", 1)
        parsed[k.strip()] = v.strip()
    metadata["isMedical"] = parsed.get("isMedical", "").lower() in ("true", "yes", "1")
    diseases = parsed.get("diseases", "")
    metadata["diseases"] = "" if diseases in ("none", "", "-") else diseases
    allergy = parsed.get("drugAllergies", "")
    metadata["drugAllergies"] = "" if allergy in ("none", "", "-") else allergy
    cleaned = _META_PATTERN.sub("", text).rstrip()
    return cleaned, metadata


router = APIRouter(prefix="/api", tags=["chat"])
_executor = ThreadPoolExecutor(max_workers=4)

# 全局存储：最近一次解读的来源元数据（供前端渲染引用面板）
_latest_sources: dict[str, list[dict]] = {}


def get_latest_sources(user_id: str) -> list[dict]:
    """获取用户最近一次解读的来源列表"""
    return _latest_sources.get(user_id, [])


def _build_report_context(report_id: str) -> tuple[str, list[dict]]:
    """
    构建报告解读上下文

    返回：
        (prompt_text, sources_list)
    """
    report = get_report(report_id)
    if report is None:
        report = get_report_pipeline().load_report(report_id)
    if report is None:
        return f"【注意：报告 {report_id} 未找到，请重新上传】", []

    engine = get_interpretation_engine()

    # 通过管线获取 RAG 知识（实际 RAG 由 Agent 在 chat 时触发，
    # 这里先构建不含 RAG 的基础 prompt，RAG 内容在 Agent 层注入）
    result = engine.build_interpretation_prompt(
        report=report,
        rag_answer="",   # RAG 由 Agent._do_rag() 在实际推理时注入
        rag_docs=None,
    )

    return result["prompt"], result["sources"]


def _run_chat(
    user_id: str,
    message: str,
    report_id: str | None,
    use_agent_loop: bool = False,
) -> tuple[str, list[dict], int]:
    """在线程池中执行同步 chat"""
    pool = get_agent_pool()
    agent = pool.get_or_create(user_id)

    sources: list[dict] = []

    if report_id and agent.state.turn_count == 0:
        report_context, sources = _build_report_context(report_id)
        enriched = f"{report_context}\n\n用户补充问题：{message}" if message.strip() else report_context
    elif report_id:
        enriched = f"（基于报告 {report_id} 的追问）\n{message}"
    else:
        enriched = message

    # Phase 5: 支持 AgentLoop 多步推理
    if use_agent_loop and agent.tools:
        reply = agent.agent_loop(enriched)
    else:
        reply = agent.chat(enriched)

    # 从 agent.state.rag_context 补充 RAG 来源
    if agent.state.rag_context:
        for line in agent.state.rag_context.split("\n"):
            if line.startswith("【来源】"):
                source_name = line.replace("【来源】", "").strip()
                if not any(s.get("source") == source_name for s in sources):
                    sources.append({
                        "source": source_name,
                        "section": "",
                        "excerpt": "",
                        "category": "rag",
                        "indicators": [],
                    })

    _latest_sources[user_id] = sources
    return reply, sources, agent.state.turn_count


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """同步对话：发送消息，返回完整回复（含结构化来源引用）"""
    try:
        loop = asyncio.get_event_loop()
        reply, sources, turn_count = await loop.run_in_executor(
            _executor,
            _run_chat,
            request.user_id,
            request.message,
            request.report_id,
            request.use_agent_loop,
        )
        return ChatResponse(
            reply=reply,
            sources=[s.get("source", "") for s in sources],
            source_details=sources,
            turn_count=turn_count,
        )
    except Exception as e:
        logger.exception("Chat endpoint error for user=%s", request.user_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/stream")
async def chat_stream(
    user_id: str = Query(default="default", description="用户 ID"),
    message: str = Query(..., min_length=1, description="用户消息"),
    report_id: str | None = Query(default=None, description="关联报告 ID"),
):
    """SSE 流式对话：逐 token 推送回复（含来源引用）"""
    pool = get_agent_pool()
    agent = pool.get_or_create(user_id)

    prepared_sources: list[dict] = []

    if report_id and agent.state.turn_count == 0:
        enriched, prepared_sources = _build_report_context(report_id)
        if message.strip():
            enriched = f"{enriched}\n\n用户补充问题：{message}"
    elif report_id:
        enriched = f"（基于报告 {report_id} 的追问）\n{message}"
    else:
        enriched = message

    async def event_generator():
        try:
            loop = asyncio.get_event_loop()
            stream_gen = agent.chat_stream(enriched)

            queue: asyncio.Queue = asyncio.Queue()

            def _produce():
                try:
                    for chunk in stream_gen:
                        queue.put_nowait(("chunk", chunk.content))
                    queue.put_nowait(("done", None))
                except Exception as e:
                    queue.put_nowait(("error", str(e)))

            loop.run_in_executor(_executor, _produce)

            while True:
                try:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'error': '推理超时'})}\n\n"
                    break

                if kind == "done":
                    break
                elif kind == "error":
                    yield f"data: {json.dumps({'error': payload})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'content': payload})}\n\n"

            # 收集 RAG 来源
            all_sources = list(prepared_sources)
            if agent.state.rag_context:
                for line in agent.state.rag_context.split("\n"):
                    if line.startswith("【来源】"):
                        src_name = line.replace("【来源】", "").strip()
                        if not any(s.get("source") == src_name for s in all_sources):
                            all_sources.append({
                                "source": src_name, "section": "",
                                "excerpt": "", "category": "rag", "indicators": [],
                            })

            _latest_sources[user_id] = all_sources

            reply_meta = {}
            yield f"data: {json.dumps({'done': True, 'sources': all_sources, 'turn_count': agent.state.turn_count, 'metadata': reply_meta}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.exception("SSE stream error for user=%s", user_id)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/sources")
async def get_chat_sources(user_id: str = Query(default="default")):
    """获取指定用户最近一次解读的知识来源引用"""
    sources = _latest_sources.get(user_id, [])
    return {"user_id": user_id, "count": len(sources), "sources": sources}
