#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from core.config import settings

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


def analyze_medical_image_comprehensive(image_input: str) -> Tuple[str, Optional[Dict[str, float]]]:
    """单次 OCR 调用，返回（文本格式、结构化 patient_labs），遵循思路文档严格流程"""
    print(f"🔴 analyze_medical_image_comprehensive 被调用了！ image_input={image_input[:80]}")
    logger.info("🔴 analyze_medical_image_comprehensive 被调用了！ image_input=%s", image_input[:80])
    try:
        logger.info("AnalyzeMedicalImage requesting OCR cache for: %s", image_input)
        full_result = _fetch_ocr_result_full(image_input=image_input, force_recheck=False, focus_item=None)
        
        ocr_text = _format_ocr_result_to_text(full_result)
        patient_labs = None
        if full_result and "gat_structured" in full_result:
            gat = full_result["gat_structured"]
            patient_labs = gat.get("patient_labs")
            if isinstance(patient_labs, dict) and patient_labs:
                logger.info("Extracted %d patient_labs from OCR result", len(patient_labs))
            else:
                patient_labs = None
        
        return ocr_text, patient_labs
    except Exception as exc:
        logger.error("AnalyzeMedicalImage failed: %s", exc, exc_info=True)
        return f"❌ 图片分析失败: {exc}", None


def analyze_medical_image(image_input: str) -> str:
    """向后兼容：仅返回文本"""
    text, _ = analyze_medical_image_comprehensive(image_input)
    return text


def extract_patient_labs_from_ocr(image_input: str) -> Optional[Dict[str, float]]:
    """向后兼容：单独提取 patient_labs（但推荐用 analyze_medical_image_comprehensive）"""
    _, labs = analyze_medical_image_comprehensive(image_input)
    return labs


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


def _fetch_ocr_result_full(image_input: str, force_recheck: bool, focus_item: Optional[str]) -> Dict[str, Any]:
    """获取 OCR 完整结果（包含 analysis, full_extraction, gat_structured）"""
    global _cached_ocr_result

    if not force_recheck and _cached_ocr_result:
        result = _cached_ocr_result
        _cached_ocr_result = None
        if _is_usable_inline_ocr_result(result):
            logger.info("Using inline OCR fallback result from Java backend")
            return result
        logger.warning(
            "Inline OCR fallback is empty/unusable, fallback to OCR service request: %s",
            image_input,
        )

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

    logger.info(
        "OCR service returned full payload (cached=%s, items=%s, mapped=%s)",
        payload.get("cached"),
        payload.get("gat_structured", {}).get("total_items", 0),
        payload.get("gat_structured", {}).get("mapped_count", 0),
    )
    return payload


def _is_usable_inline_ocr_result(result: Optional[Dict[str, Any]]) -> bool:
    """判断 Java 直传 OCR 回退结果是否可直接用于分析。"""
    if not isinstance(result, dict):
        return False

    analysis_items = result.get("analysis")
    if isinstance(analysis_items, list) and len(analysis_items) > 0:
        return True

    gat_structured = result.get("gat_structured")
    if isinstance(gat_structured, dict):
        patient_labs = gat_structured.get("patient_labs")
        if isinstance(patient_labs, dict) and len(patient_labs) > 0:
            return True
        mapped_count = gat_structured.get("mapped_count", 0)
        try:
            return int(mapped_count) > 0
        except Exception:
            return False

    return False


def _fetch_ocr_result(image_input: str, force_recheck: bool, focus_item: Optional[str]) -> List[Any]:
    """向后兼容：只返回 analysis 部分"""
    full = _fetch_ocr_result_full(image_input, force_recheck, focus_item)
    return full.get("analysis", [])


def _parse_recheck_payload(payload: str) -> tuple[str, str]:
    parts = [part.strip() for part in payload.split("||", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("请使用 `图片路径||重点复核项目` 的格式调用")
    return parts[0], parts[1]


def _format_ocr_result_to_text(ocr_result: Dict[str, Any]) -> str:
    analysis_items = ocr_result.get("analysis", []) or []
    full_extraction = ocr_result.get("full_extraction", []) or []
    gat_structured = ocr_result.get("gat_structured", {}) or {}
    patient_labs = gat_structured.get("patient_labs", {}) or {}

    if not analysis_items and not full_extraction and not patient_labs:
        return "化验单识别结果为空"

    lines = ["【化验单识别结果（全量）】", ""]
    seen = set()

    # 1) 首段优先展示完整提取，保证“第一段”看到全量内容
    if full_extraction:
        lines.append("【完整提取】")
        for row in full_extraction:
            text = str(row).strip()
            if not text or text in seen:
                continue
            lines.append(f"- {text}")
            seen.add(text)
        lines.append("")

    # 2) 展示结构化指标（供后续ReAct/GAT使用的数据）
    if patient_labs:
        lines.append("【结构化指标（patient_labs）】")
        for key in sorted(patient_labs.keys()):
            val = patient_labs.get(key)
            line = f"- {key}: {val}"
            lines.append(line)
            seen.add(line)
        lines.append("")

    # 3) 回退展示 analysis，避免遗漏未结构化字段
    if analysis_items:
        lines.append("【OCR分析明细】")
        for item in analysis_items:
            if isinstance(item, str):
                text = f"- {item.strip()}"
            elif isinstance(item, dict):
                name = item.get("item") or item.get("name") or "未知项目"
                value = item.get("value") or "N/A"
                unit = item.get("unit") or ""
                normal_range = item.get("normal_range") or "N/A"
                status = item.get("status") or "未知"
                text = f"- {name}: {value} {unit} (正常范围: {normal_range}) [{status}]"
            else:
                text = f"- {str(item)}"

            if text in seen:
                continue
            lines.append(text)
            seen.add(text)

    return "\n".join(lines)
