"""
聊天路由：ReAct 多步推理 SSE 流式对话

每个 (user_id, session_id) 对应一个 analyze_ReActLoop 实例，
通过 emit 回调 + asyncio.Queue 实时推送推理步骤。
"""

from __future__ import annotations
import json
import logging
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.routes.report import get_report
from app.business.report_pipeline import get_report_pipeline
from harness.agentic_loop.analyze_ReAct_loop import analyze_ReActLoop
from harness.memory.long_term.memory_snapshot import MemorySnapshotMemory
from harness.memory.persistence.repositories.memory_snapshot_repo import MemorySnapshotRepo

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

# 每个 (user_id, session_id) 对应一个 loop 实例
_loops: dict[tuple, analyze_ReActLoop] = {}


def _get_or_create_loop(user_id: str, session_id: str, max_steps: int = 5) -> analyze_ReActLoop:
    key = (user_id, session_id)
    if key not in _loops:
        _loops[key] = analyze_ReActLoop(
            user_id=user_id,
            session_id=session_id,
            max_steps=max_steps,
        )
    return _loops[key]


def _build_report_context(report_id: str) -> str:
    """将化验报告转化为字符串"""
    report = get_report(report_id)
    if report is None:
        report = get_report_pipeline().load_report(report_id)
    if report is None:
        return f"【注意：报告 {report_id} 未找到，请重新上传】"
    return report.to_context_text()


@router.get("/chat/history")
async def get_chat_history(
    user_id: str = Query(default="default"),
    session_id: str = Query(...),
):
    """从快照恢复最新一轮对话历史"""
    snapshot = MemorySnapshotMemory(MemorySnapshotRepo())
    data = snapshot.load(user_id, session_id)
    if not data:
        return {"code": 200, "data": {"messages": []}}

    messages = [
        m for m in data["messages"]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return {"code": 200, "data": {"messages": messages}}


@router.get("/chat/react-stream")
async def chat_react_stream(
    user_id: str = Query(default="default", description="用户 ID"),
    session_id: str = Query(default="default", description="会话 ID"),
    message: str = Query(..., min_length=1, description="用户消息"),
    report_id: str | None = Query(default=None, description="关联报告 ID"),
    max_steps: int = Query(default=5, ge=1, le=10, description="最大推理步数"),
):
    """SSE 流式 ReAct 推理"""
    loop = _get_or_create_loop(user_id, session_id, max_steps)

    query = []
    if report_id:
        report_context = _build_report_context(report_id)
        query.append(report_context)
    query.append(message)

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def emit(event: dict):
            queue.put_nowait(event)

        def blocking_run():
            try:
                loop.run(query, emit=emit)
            except Exception as e:
                logger.exception("ReAct loop error for user=%s session=%s", user_id, session_id)
                queue.put_nowait({"type": "error", "message": str(e)})
            finally:
                queue.put_nowait(None)

        executor = ThreadPoolExecutor(max_workers=1)
        asyncio.get_event_loop().run_in_executor(executor, blocking_run)

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=180.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'message': '推理超时'}, ensure_ascii=False)}\n\n"
                break
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
