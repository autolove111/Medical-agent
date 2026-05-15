import logging
from typing import Optional

from langchain_core.tools import Tool

from .history import query_user_age_profile, query_user_medical_history
from .ocr import analyze_medical_image, recheck_medical_image

logger = logging.getLogger(__name__)


def query_medical_knowledge(
    keyword: str,
    indicator: Optional[str] = None,
    direction: Optional[str] = None,
) -> str:
    composed = (keyword or "").strip()
    if indicator:
        composed = f"{composed} {indicator}".strip()
    if direction:
        dir_text = {"high": "high", "low": "low", "normal": "normal"}.get(direction, str(direction))
        composed = f"{composed} {dir_text}".strip()

    logger.info(
        "[TOOLS][Knowledge] start | keyword=%s",
        composed[:160],
    )

    try:
        from knowledge.rag import retrieve_medical_knowledge as retrieve_via_rag

        result, _sources = retrieve_via_rag(composed)
        if result and str(result).strip():
            logger.info("[TOOLS][Knowledge] done(rag)")
            return result
    except Exception as exc:
        logger.debug("RAG query failed, fallback to local knowledge base: %s", exc)

    return "No knowledge result available."


def classify_medical_report(content: str) -> str:
    text = (content or "").lower()
    if any(k in text for k in ["cbc", "wbc", "rbc", "hemoglobin", "plt"]):
        return "blood_test"
    if any(k in text for k in ["alt", "ast", "bilirubin", "ggt", "alp"]):
        return "liver_test"
    if any(k in text for k in ["creatinine", "bun", "urea", "egfr", "uric"]):
        return "kidney_test"
    if any(k in text for k in ["glucose", "hba1c", "thyroid", "tsh"]):
        return "metabolic_test"
    return "medical_report"


tools = [
    Tool(
        name="QueryMedicalKnowledge",
        func=query_medical_knowledge,
        description="Query shared medical knowledge or RAG content.",
    ),
    Tool(
        name="QueryUserHistory",
        func=query_user_medical_history,
        description="Query the user's medical history.",
    ),
    Tool(
        name="QueryUserAgeProfile",
        func=query_user_age_profile,
        description="Query the user's age profile.",
    ),
    Tool(
        name="ClassifyReport",
        func=classify_medical_report,
        description="Classify a medical report type.",
    ),
    Tool(
        name="AnalyzeMedicalImage",
        func=analyze_medical_image,
        description="Analyze a medical report image.",
    ),
    Tool(
        name="RecheckMedicalImage",
        func=recheck_medical_image,
        description="Recheck OCR results with a focus item.",
    ),
]


__all__ = ["classify_medical_report", "query_medical_knowledge", "tools"]
