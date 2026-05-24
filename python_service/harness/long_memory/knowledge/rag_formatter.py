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
