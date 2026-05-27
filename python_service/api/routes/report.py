"""
报告路由：上传化验单 → OCR 识别 → 结构化提取 → 指标分类 → 联动分析

Phase 4：SQLite 持久化（DB + JSON 双写）
"""

from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.models import ReportUploadResponse, IndicatorItem
from app.business.report_pipeline import get_report_pipeline
from app.business.lab_report import LabReport
from app.persistence.repositories.report_repo import ReportRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report", tags=["report"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")

# ---- 全局报告存储（内存缓存，后续 Phase 4 迁移至 SQLite） ----
_report_store: dict[str, LabReport] = {}


def get_report(report_id: str) -> Optional[LabReport]:
    """获取已处理的报告"""
    return _report_store.get(report_id)


def set_report(report: LabReport):
    """缓存报告"""
    _report_store[report.report_id] = report


@router.post("/upload", response_model=ReportUploadResponse)
async def upload_report(
    file: UploadFile = File(..., description="化验单图片或 PDF"),
    user_id: str = Form(default="default"),
    report_date: Optional[str] = Form(default=None, description="检验日期 YYYY-MM-DD"),
    age: int = Form(default=0, description="患者年龄"),
    gender: str = Form(default="", description="患者性别 男/女"),
):
    """
    上传化验单，自动 OCR 识别并结构化。

    管线流程：
    1. 保存文件 → 2. 调 OCR 服务 → 3. 结构化提取
    → 4. 40+ 参考范围匹配（含年龄/性别分层）
    → 5. 危急值检测 → 6. 多指标联动分析
    → 7. 生成解读 prompt → 8. 持久化
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

    # ---- 接入完整管线 ----
    pipeline = get_report_pipeline()

    # Step 1: 调用 OCR
    try:
        ocr_result = await pipeline.call_ocr(save_path)
    except Exception as e:
        logger.exception("OCR failed for %s", save_path)
        raise HTTPException(status_code=502, detail=f"OCR 识别服务不可用: {e}")

    # Step 2: 构建结构化报告（含 40+ 参考范围匹配 + 年龄/性别分层）
    if not report_date:
        report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    report = pipeline.build_report(
        user_id=user_id,
        file_path=save_path,
        ocr_result=ocr_result,
        report_date=report_date,
        age=age,
        gender=gender,
    )

    # Step 3: 联动分析
    correlations = pipeline.analyze_correlations(report)

    # Step 4: 持久化（JSON 文件 + SQLite 数据库双写）
    pipeline.save_report(report)
    set_report(report)

    try:
        ReportRepo().save(
            report_id=report.report_id,
            user_id=report.user_id,
            report_date=report.report_date,
            file_path=report.file_path,
            total_count=report.total_count,
            abnormal_count=report.abnormal_count,
            normal_count=report.normal_count,
            has_critical=report.has_critical,
            indicators=[ind.to_dict() for ind in report.indicators],
            correlations=[
                {"name": m.name, "severity": m.severity,
                 "indicators": m.matched_indicators, "description": m.description,
                 "suggestion": m.suggestion_hint}
                for m in corr_matches
            ],
            raw_ocr_text=report.raw_ocr_text,
        )
        logger.info("Report %s persisted to SQLite", report.report_id)
    except Exception as e:
        logger.warning("Failed to persist report to DB: %s", e)

    # ---- 构建 API 响应 ----
    api_indicators = [
        IndicatorItem(
            key=ind.key,
            name=ind.name,
            value=ind.value,
            unit=ind.unit,
            ref_range=ind.ref_range,
            status=ind.status,
        )
        for ind in report.indicators
    ]

    # 联动分析摘要
    corr_matches = correlations.get("matches", [])
    corr_summary = [m.name for m in corr_matches] if corr_matches else []

    logger.info(
        "Report %s: %d indicators (%d abnormal, %d critical), %d correlations",
        report.report_id, report.total_count, report.abnormal_count,
        len(report.get_critical_indicators()), len(corr_matches),
    )

    return ReportUploadResponse(
        report_id=report.report_id,
        indicators=api_indicators,
        abnormal_count=report.abnormal_count,
        normal_count=report.normal_count,
        raw_ocr_text=report.raw_ocr_text[:5000],  # 限制返回长度
    )


@router.get("/{report_id}")
async def get_report_detail(report_id: str):
    """获取已处理报告的完整详情（DB 优先，回退 JSON 文件）"""
    repo = ReportRepo()
    db_report = repo.get_full(report_id)

    if db_report is not None:
        # 从 DB 获取
        report = get_report(report_id)  # 尝试获取内存中的联动分析
        if report is None:
            report = get_report_pipeline().load_report(report_id)

        correlations_data = db_report.get("correlations", [])
        if report is not None:
            correlations = get_report_pipeline().analyze_correlations(report)
            corr_matches = correlations.get("matches", [])
            if corr_matches:
                correlations_data = [
                    {"name": m.name, "severity": m.severity,
                     "indicators": m.matched_indicators,
                     "description": m.description,
                     "suggestion": m.suggestion_hint}
                    for m in corr_matches
                ]

        return {
            "report": db_report,
            "correlations": correlations_data,
            "correlation_context": "",
            "interpretation_prompt": "",
        }

    # 回退：从内存/文件加载
    report = get_report(report_id)
    if report is None:
        report = get_report_pipeline().load_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"报告 {report_id} 不存在")

    pipeline = get_report_pipeline()
    correlations = pipeline.analyze_correlations(report)
    corr_matches = correlations.get("matches", [])
    corr_data = [
        {"name": m.name, "severity": m.severity,
         "indicators": m.matched_indicators,
         "description": m.description,
         "suggestion": m.suggestion_hint}
        for m in corr_matches
    ]
    return {
        "report": report.to_dict(),
        "correlations": corr_data,
        "correlation_context": correlations.get("context_text", ""),
        "interpretation_prompt": pipeline.generate_interpretation_prompt(report, correlations),
    }


@router.get("/user/{user_id}/list")
async def list_user_reports(user_id: str):
    """列出用户的所有历史报告摘要（DB 优先）"""
    repo = ReportRepo()
    db_reports = repo.list_by_user(user_id)

    if db_reports:
        return {"user_id": user_id, "total": len(db_reports), "reports": db_reports, "source": "database"}

    # 回退 JSON 文件
    pipeline = get_report_pipeline()
    reports = pipeline.list_user_reports(user_id)
    return {"user_id": user_id, "total": len(reports), "reports": reports, "source": "json_files"}
