"""
RAG 路由

提供 /rag/query 端点，知识库检索。
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/query")
async def rag_query(query: str, top_k: int = 3):
    """RAG 检索"""
    try:
        from rag import retrieve_medical_knowledge
        answer, docs = retrieve_medical_knowledge(query)
        return {
            "answer": answer,
            "documents": [
                {"content": doc.get_content()[:500], "metadata": doc.metadata}
                for doc in (docs or [])
            ],
        }
    except Exception as e:
        logger.error("RAG query failed: %s", e, exc_info=True)
        return {"error": str(e)}
