"""
报告路由：上传化验单 → 入队列异步 OCR → 前端轮询结果

流程：
  1. POST /upload        → 存文件 + 入队列，立即返回 task_id
  2. GET  /ocr-status/{task_id} → 轮询 OCR 处理状态和结果
  3. OCR Worker 后台消费队列，处理完写 Redis + Pub/Sub 通知
"""

from __future__ import annotations
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.models import ReportUploadResponse, IndicatorItem
from app.core.config import settings

# OCR 测试接口仍需直接调用
from ocr.ocr_service import call_mineru
from indicator_analyse.indicator_analyse import parse_markdown_to_patient_labs

# 消息队列
from broker.redis_broker import (
    submit_ocr_request, get_task_status, update_task_status, expire_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report", tags=["report"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")


def format_ocr_result(user_name: str, indicators: list[dict]) -> str:
    """格式化 OCR 结果为用户消息格式"""
    lines = [f"我是{user_name}，这是我的化验单结果："]

    for i in indicators:
        status_map = {
            "high": "↑",
            "low": "↓",
            "critical_high": "↑↑危急",
            "critical_low": "↓↓危急",
            "normal": "",
        }
        flag = status_map.get(i["status"], "")
        lines.append(f"{i['name']}（{i['key']}）：{i['value']} {i['unit']} [参考:{i['ref_range']}] {flag}")

    return "\n".join(lines)


def format_report_analysis(indicators: list[dict]) -> str:
    """格式化分析结果为助手消息格式"""
    abnormal = [i for i in indicators if i["status"] != "normal"]
    normal_count = sum(1 for i in indicators if i["status"] == "normal")

    lines = [
        f"📊 化验报告分析：",
        f"共 {len(indicators)} 项指标，正常 {normal_count} 项，异常 {len(abnormal)} 项",
        "",
    ]

    if abnormal:
        lines.append("⚠️ 异常指标分析：")
        status_map = {
            "high": "⬆️ 偏高",
            "low": "⬇️ 偏低",
            "critical_high": "🚨 危急偏高",
            "critical_low": "🚨 危急偏低",
        }
        for i in abnormal:
            status_text = status_map.get(i["status"], i["status"])
            lines.append(f"  - {i['name']}：{i['value']} {i['unit']} ({status_text})")
    else:
        lines.append("✅ 所有指标均在正常范围内。")

    return "\n".join(lines)


@router.post("/test-ocr")
async def test_ocr(
    file: UploadFile = File(..., description="化验单图片或 PDF"),
):
    """
    OCR 测试接口：只跑 MinerU OCR，不做指标分析、不存记忆。
    用于调试 OCR 识别准确度。
    """
    allowed_types = ["image/jpeg", "image/png", "image/webp", "application/pdf"]
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}")

    # 保存临时文件
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "report.jpg")[1] or ".jpg"
    safe_name = f"test_{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, safe_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    logger.info("[test-ocr] File saved: %s (%d bytes)", save_path, len(content))

    # 调用 MinerU OCR → 原始 Markdown
    try:
        raw_markdown = await call_mineru(save_path)
        patient_labs = parse_markdown_to_patient_labs(raw_markdown)
    except Exception as e:
        logger.exception("[test-ocr] OCR failed for %s", save_path)
        raise HTTPException(status_code=502, detail=f"OCR 识别失败: {e}")
    finally:
        # 清理临时文件
        try:
            os.remove(save_path)
        except OSError:
            pass

    return {
        "patient_labs": patient_labs,
        "indicators_count": len(patient_labs),
        "raw_markdown": raw_markdown,
    }


@router.post("/upload")
async def upload_report(
    file: UploadFile = File(..., description="化验单图片或 PDF"),
    user_id: str = Form(default="default"),
    session_id: str = Form(default="default"),
    age: int = Form(default=0),
    gender: str = Form(default=""),
):
    """
    上传化验单，异步 OCR。

    流程：保存文件 → 入队列 → 立即返回 task_id
    前端通过 GET /ocr-status/{task_id} 轮询结果，或等待 WebSocket 通知。
    """
    # 校验文件类型
    allowed_types = ["image/jpeg", "image/png", "image/webp", "application/pdf"]
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}")

    # 保存到 uploads/
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "report.jpg")[1] or ".jpg"
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, safe_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    logger.info("File saved: %s (%d bytes)", save_path, len(content))

    # 生成 task_id，写入初始状态，提交到 OCR 队列
    task_id = str(uuid.uuid4())
    update_task_status(task_id, "queued", task_type="ocr",
                       user_id=user_id, session_id=session_id,
                       file_path=save_path, file_type="image",
                       age=age, gender=gender)

    # 设置 TTL（2 小时）
    from broker.redis_broker import expire_task
    expire_task(task_id, task_type="ocr", ttl=7200)

    submit_ocr_request(task_id, save_path, file_type="image")

    logger.info("OCR task queued | task_id=%s user=%s", task_id, user_id)

    # 立即返回，不等 OCR
    return {"task_id": task_id, "status": "queued", "message": "化验单已提交识别，请等待结果"}


@router.get("/ocr-status/{task_id}")
async def get_ocr_status(task_id: str):
    """
    查询 OCR 任务状态。

    状态流转：queued → processing → done / error
    done 时返回完整报告数据。
    """
    status_data = get_task_status(task_id, task_type="ocr")
    if not status_data:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    status = status_data.get("status", "unknown")

    result = {
        "task_id": task_id,
        "status": status,
    }

    # done 时带上完整结果
    if status == "done":
        # 从 Redis Hash 中取出各字段
        def _load(key):
            val = status_data.get(key)
            if val and isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return val
            return val

        result["report_id"] = status_data.get("report_id")
        result["report_date"] = status_data.get("report_date", "")
        result["indicators"] = _load("indicators") or []
        result["abnormal_count"] = int(status_data.get("abnormal_count", 0))
        result["normal_count"] = int(status_data.get("normal_count", 0))
        result["raw_markdown"] = status_data.get("raw_markdown", "")

    elif status == "error":
        result["error"] = status_data.get("error", "未知错误")

    return result


@router.get("/user/{user_id}/session/{session_id}")
async def get_session_report(user_id: str, session_id: str):
    """从短期记忆获取会话中的对话消息"""
    from memory.short_memory.store import ShortMemoryStore
    try:
        store = ShortMemoryStore(user_id=user_id, session_id=session_id)
        messages = store.messages

        return {
            "messages": messages,
        }
    except Exception as e:
        logger.error("Failed to get session report: %s", e)
        return {"status": "error", "message": str(e)}
