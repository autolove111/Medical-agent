from typing import Dict, Iterable, List

from langchain_core.documents import Document


def serialize_documents(documents: Iterable[Document]) -> List[Dict]:
    serialized: List[Dict] = []
    for document in documents:
        serialized.append(
            {
                "page_content": document.page_content,
                "metadata": getattr(document, "metadata", {}) or {},
            }
        )
    return serialized


def deserialize_documents(items: Iterable[Dict]) -> List[Document]:
    documents: List[Document] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        documents.append(
            Document(
                page_content=item.get("page_content", ""),
                metadata=item.get("metadata", {}),
            )
        )
    return documents


def format_documents_as_answer(documents: Iterable[Document]) -> str:
    context_list: List[str] = []
    for document in documents:
        source_name = getattr(document, "metadata", {}).get("source", "unknown")
        context_list.append(f"【来源】{source_name}\n{document.page_content}")
    return "\n\n".join(context_list)


def extract_source_metadata(documents: Iterable[Document]) -> List[dict]:
    """
    从 Document 列表中提取结构化来源元数据

    返回：[{"source": "肾脏医学指南.txt", "excerpt": "肌酐是肾功能...", "section": "慢性肾脏病", ...}, ...]
    """
    sources: List[dict] = []
    seen = set()

    for doc in documents:
        metadata = getattr(doc, "metadata", {}) or {}
        source_name = metadata.get("source", "unknown")
        page_content = getattr(doc, "page_content", "") or ""

        # 提取章节
        section = ""
        for line in page_content.split("\n"):
            line = line.strip()
            if line.startswith("## ") or line.startswith("# "):
                section = line.lstrip("# ").strip()
                break

        # 去重
        key = f"{source_name}:{section}"
        if key in seen:
            continue
        seen.add(key)

        sources.append({
            "source": source_name,
            "section": section,
            "excerpt": page_content[:200].strip(),
            "char_count": len(page_content),
        })

    return sources
