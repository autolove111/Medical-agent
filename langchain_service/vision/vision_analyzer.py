#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_cached_ocr_result: Optional[Dict[str, Any]] = None


def set_ocr_result(ocr_result: Dict[str, Any]) -> None:
    global _cached_ocr_result
    _cached_ocr_result = ocr_result


def analyze_medical_image_comprehensive(image_input: str) -> Tuple[str, Optional[Dict[str, float]]]:
    try:
        full_result = _fetch_ocr_result_full(image_input=image_input, force_recheck=False, focus_item=None)
        ocr_text = _format_ocr_result_to_text(full_result)
        patient_labs = None
        if full_result and "gat_structured" in full_result:
            gat = full_result["gat_structured"]
            patient_labs = gat.get("patient_labs")
            if not isinstance(patient_labs, dict) or not patient_labs:
                patient_labs = None
        return ocr_text, patient_labs
    except Exception as exc:
        logger.error("AnalyzeMedicalImage failed: %s", exc, exc_info=True)
        return f"OCR failed: {exc}", None


def analyze_medical_image(image_input: str) -> str:
    text, _ = analyze_medical_image_comprehensive(image_input)
    return text


def extract_patient_labs_from_ocr(image_input: str) -> Optional[Dict[str, float]]:
    _, labs = analyze_medical_image_comprehensive(image_input)
    return labs


def recheck_medical_image(payload: str) -> str:
    try:
        image_input, focus_item = _parse_recheck_payload(payload)
        result = _fetch_ocr_result(image_input=image_input, force_recheck=True, focus_item=focus_item)
        return _format_ocr_result_to_text({"analysis": result})
    except Exception as exc:
        logger.error("RecheckMedicalImage failed: %s", exc, exc_info=True)
        return f"Recheck failed: {exc}"


def _fetch_ocr_result_full(image_input: str, force_recheck: bool, focus_item: Optional[str]) -> Dict[str, Any]:
    global _cached_ocr_result

    if not force_recheck and _cached_ocr_result:
        result = _cached_ocr_result
        _cached_ocr_result = None
        if _is_usable_inline_ocr_result(result):
            return result

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
    return response.json()


def _is_usable_inline_ocr_result(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    analysis_items = result.get("analysis")
    if isinstance(analysis_items, list) and analysis_items:
        return True
    gat_structured = result.get("gat_structured")
    if isinstance(gat_structured, dict):
        patient_labs = gat_structured.get("patient_labs")
        if isinstance(patient_labs, dict) and patient_labs:
            return True
    return False


def _fetch_ocr_result(image_input: str, force_recheck: bool, focus_item: Optional[str]) -> List[Any]:
    full = _fetch_ocr_result_full(image_input, force_recheck, focus_item)
    return full.get("analysis", [])


def _parse_recheck_payload(payload: str) -> tuple[str, str]:
    parts = [part.strip() for part in payload.split("||", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Use `image_path||focus_item` format")
    return parts[0], parts[1]


def _format_ocr_result_to_text(ocr_result: Dict[str, Any]) -> str:
    analysis_items = ocr_result.get("analysis", []) or []
    full_extraction = ocr_result.get("full_extraction", []) or []
    gat_structured = ocr_result.get("gat_structured", {}) or {}
    patient_labs = gat_structured.get("patient_labs", {}) or {}

    if not analysis_items and not full_extraction and not patient_labs:
        return "No OCR content."

    lines = ["OCR result:", ""]
    if full_extraction:
        lines.append("Full extraction:")
        for row in full_extraction:
            text = str(row).strip()
            if text:
                lines.append(f"- {text}")
        lines.append("")

    if patient_labs:
        lines.append("Structured labs:")
        for key in sorted(patient_labs.keys()):
            lines.append(f"- {key}: {patient_labs.get(key)}")
        lines.append("")

    if analysis_items:
        lines.append("Analysis:")
        for item in analysis_items:
            if isinstance(item, str):
                text = f"- {item.strip()}"
            elif isinstance(item, dict):
                name = item.get("item") or item.get("name") or "unknown"
                value = item.get("value") or "N/A"
                unit = item.get("unit") or ""
                normal_range = item.get("normal_range") or "N/A"
                status = item.get("status") or "unknown"
                text = f"- {name}: {value} {unit} (normal: {normal_range}) [{status}]"
            else:
                text = f"- {str(item)}"
            lines.append(text)

    return "\n".join(lines)
