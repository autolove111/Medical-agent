#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_cached_ocr_result: Optional[Dict[str, Any]] = None


def set_ocr_result(ocr_result: Dict[str, Any]) -> None:
    """
    Compatibility hook for the old Java -> Agent direct OCR handoff path.
    The new architecture prefers hitting the OCR cache service on port 8001.
    """
    global _cached_ocr_result
    _cached_ocr_result = ocr_result
    if ocr_result:
        logger.info("Received inline OCR result fallback from Java backend")


def analyze_medical_image(image_input: str) -> str:
    try:
        logger.info("AnalyzeMedicalImage requesting OCR cache for: %s", image_input)
        result = _fetch_ocr_result(image_input=image_input, force_recheck=False, focus_item=None)
        return _format_ocr_result_to_text({"analysis": result})
    except Exception as exc:
        logger.error("AnalyzeMedicalImage failed: %s", exc, exc_info=True)
        return f"❌ 图片分析失败: {exc}"


def recheck_medical_image(payload: str) -> str:
    """
    Payload format: image_path||focus_item
    """
    try:
        image_input, focus_item = _parse_recheck_payload(payload)
        logger.info("RecheckMedicalImage requesting force recheck for: %s focus=%s", image_input, focus_item)
        result = _fetch_ocr_result(image_input=image_input, force_recheck=True, focus_item=focus_item)
        return _format_ocr_result_to_text({"analysis": result})
    except Exception as exc:
        logger.error("RecheckMedicalImage failed: %s", exc, exc_info=True)
        return f"❌ 二次核对失败: {exc}"


def _fetch_ocr_result(image_input: str, force_recheck: bool, focus_item: Optional[str]) -> List[Dict[str, Any]]:
    global _cached_ocr_result

    if not force_recheck and _cached_ocr_result and _cached_ocr_result.get("analysis"):
        logger.info("Using inline OCR fallback result from Java backend")
        analysis = _cached_ocr_result.get("analysis", [])
        _cached_ocr_result = None
        return analysis

    with httpx.Client(timeout=settings.OCR_SERVICE_TIMEOUT, trust_env=False) as client:
        response = client.post(
            f"{settings.OCR_SERVICE_URL}/api/v1/analyze-vision",
            json={
                "path": image_input,
                "force_recheck": force_recheck,
                "focus_item": focus_item,
            },
        )
    response.raise_for_status()
    payload = response.json()
    analysis = payload.get("analysis")
    if not isinstance(analysis, list):
        raise ValueError("OCR service returned invalid analysis payload")

    logger.info(
        "OCR service returned %s items (cached=%s)",
        len(analysis),
        payload.get("cached"),
    )
    return analysis


def _parse_recheck_payload(payload: str) -> tuple[str, str]:
    parts = [part.strip() for part in payload.split("||", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("请使用 `图片路径||重点复核项目` 的格式调用")
    return parts[0], parts[1]


def _format_ocr_result_to_text(ocr_result: Dict[str, Any]) -> str:
    analysis_items = ocr_result.get("analysis", [])
    if not analysis_items:
        return "化验单识别结果为空"

    lines = ["【化验单识别结果】", ""]
    for item in analysis_items:
        name = item.get("item") or item.get("name") or "未知项目"
        value = item.get("value") or "N/A"
        unit = item.get("unit") or ""
        normal_range = item.get("normal_range") or "N/A"
        status = item.get("status") or "未知"
        lines.append(f"- {name}: {value} {unit} (正常范围: {normal_range}) [{status}]")
    return "\n".join(lines)
