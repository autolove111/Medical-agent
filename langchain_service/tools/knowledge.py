from typing import Optional
import logging

from langchain_core.tools import Tool

from core.config import settings
from .history import query_user_age_profile, query_user_medical_history
from .ocr import analyze_medical_image, recheck_medical_image

logger = logging.getLogger(__name__)


def query_medical_knowledge(
    keyword: str,
    scope: str = "main",
    department: Optional[str] = None,
    indicator: Optional[str] = None,
    direction: Optional[str] = None,
) -> str:
    composed = (keyword or "").strip()
    if indicator:
        composed = f"{composed} {indicator}".strip()
    if direction:
        dir_text = {"high": "升高", "low": "降低", "normal": "正常"}.get(direction, str(direction))
        composed = f"{composed} {dir_text}".strip()

    logger.info(
        "[TOOLS][Knowledge] start | scope=%s dept=%s keyword=%s",
        scope,
        department,
        (composed or "")[:160],
    )

    try:
        from knowledge.rag import retrieve_medical_knowledge as retrieve_via_rag

        result, sources = retrieve_via_rag(composed, scope=scope, department=department)
        if result and str(result).strip():
            logger.info(
                "[TOOLS][Knowledge] done(rag) | scope=%s dept=%s chars=%d sources=%d",
                scope,
                department,
                len(result),
                len(sources or []),
            )
            return result
    except Exception:
        logger.debug("rag module not available or failed")

    try:
        from knowledge.medical_knowledge import create_knowledge_base

        kb = create_knowledge_base()
        if not kb:
            return (
                "【知识库未初始化】无法执行 embeddings 检索。"
                " 请在 `langchain_service/.env` 中设置 `DASHSCOPE_API_KEY`，并运行向量构建脚本。"
            )

        if not getattr(kb, "vectorstore", None):
            return (
                "【向量索引缺失】本地 KnowledgeBase 未构建向量索引。"
                " 请运行: python -m langchain_service.knowledge.build_vectorstore"
            )

        retriever = kb.vectorstore.as_retriever(search_kwargs={"k": getattr(settings, "RAG_TOP_K", 3)})
        docs = retriever.get_relevant_documents(composed)
        if not docs:
            logger.info("[TOOLS][Knowledge] empty(vector) | scope=%s dept=%s", scope, department)
            return f"【知识库检索结果】未找到关键字 '{composed}' 的相关医学文献"

        snippets = []
        for d in docs:
            src = getattr(d, "metadata", {}).get("source", "local")
            snippets.append(f"【{src}】 {d.page_content[:800].strip()}")

        out_text = "\n\n".join(snippets)
        logger.info("[TOOLS][Knowledge] done(vector) | scope=%s dept=%s snippets=%d", scope, department, len(snippets))
        return "【知识库检索结果】\n" + out_text
    except Exception as e:
        logger.exception("Embeddings 检索异常: %s", e)
        return "【检索异常】Embeddings 检索失败：" + str(e) + "。"


def classify_medical_report(content: str) -> str:
    keywords_map = {
        "血液": "血液检查",
        "CBC": "血液检查",
        "肝功": "肝功能检查",
        "Liver": "肝功能检查",
        "肾功": "肾功能检查",
        "Kidney": "肾功能检查",
        "血糖": "代谢检查",
        "葡萄糖": "代谢检查",
        "心电": "心脏检查",
        "ECG": "心脏检查",
        "尿": "尿液检查",
        "Urine": "尿液检查",
    }

    for keyword, classification in keywords_map.items():
        if keyword in content:
            return classification

    return "综合医学报告"


tools = [
    Tool(
        name="QueryMedicalKnowledge",
        func=query_medical_knowledge,
        description="从医学知识库查询相关医学信息。输入：医学关键词。",
    ),
    Tool(
        name="QueryUserHistory",
        func=query_user_medical_history,
        description="查询当前用户的既往史、过敏信息。输入必须是 UUID 格式的 user_id。",
    ),
    Tool(
        name="QueryUserAgeProfile",
        func=query_user_age_profile,
        description="查询当前用户年龄画像。输入必须是 UUID 格式的 user_id，返回 age_years/is_pediatric。",
    ),
    Tool(
        name="ClassifyReport",
        func=classify_medical_report,
        description="自动分类医疗报告类型。输入：报告内容。",
    ),
    Tool(
        name="AnalyzeMedicalImage",
        func=analyze_medical_image,
        description=(
            "分析医学化验单图片。输入图片本地路径或 URL。"
            "该工具会先访问 OCR 缓存服务；如果 Java 已提前预取，通常会直接命中缓存。"
        ),
    ),
    Tool(
        name="RecheckMedicalImage",
        func=recheck_medical_image,
        description="对 OCR 结果做高精度二次核对。输入格式必须是 图片路径||重点复核项目 。",
    ),
]


__all__ = ["classify_medical_report", "query_medical_knowledge", "tools"]

