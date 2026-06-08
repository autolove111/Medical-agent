"""Minimal medical knowledge shim with shared multi-format loaders."""

from typing import Any, Dict, List, Optional, Tuple
import logging
import os

from core.config import settings
from service.rag.document_loaders import iter_supported_document_files, load_text_documents
from .reference_ranges import get_reference_range

logger = logging.getLogger(__name__)


try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
except Exception:
    RecursiveCharacterTextSplitter = None
    FAISS = None
    Document = None

from service.rag.embedding import create_embeddings


class KnowledgeBase:
    """Load local medical corpus and optionally build a FAISS vector store."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.docs: List[Dict[str, Any]] = []
        self.vectorstore = None
        self.embeddings = None
        self._load_text_corpus()
        try:
            self._build_vectorstore()
        except Exception as exc:
            logger.warning("Knowledge base vector build failed, fallback to plain text search: %s", exc)

    def _load_text_corpus(self):
        data_dir = os.path.join(self.base_dir, "data")
        candidates = [
            os.path.join(data_dir, "dept_agent_docs"),
            os.path.join(data_dir, "main_agent_docs"),
            os.path.join(data_dir, "medical_docs"),
        ]

        for directory in candidates:
            if not os.path.isdir(directory):
                continue

            for path in iter_supported_document_files(directory):
                try:
                    for document in load_text_documents(path):
                        self.docs.append(
                            {
                                "source": os.path.relpath(path, self.base_dir),
                                "path": path,
                                "text": document.page_content,
                            }
                        )
                except Exception as exc:
                    logger.warning("Failed to load knowledge document %s: %s", path, exc)

        logger.info("KnowledgeBase loaded %s document chunks", len(self.docs))

    def _build_vectorstore(self):
        if not FAISS or not RecursiveCharacterTextSplitter:
            raise RuntimeError("Missing vector-store dependencies")
        self.embeddings = create_embeddings(purpose="rag")

        corpus_paths = list(dict.fromkeys(doc["path"] for doc in self.docs))

        documents: List[Document] = []
        for path in corpus_paths:
            documents.extend(load_text_documents(path))

        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = splitter.split_documents(documents)
        if not chunks:
            raise RuntimeError("No chunks were generated from the knowledge corpus")

        vectorstore = None
        batch_size = 10
        for index in range(0, len(chunks), batch_size):
            batch = chunks[index:index + batch_size]
            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch, self.embeddings)
            else:
                vectorstore.add_documents(batch)

        self.vectorstore = vectorstore
        logger.info("KnowledgeBase vector store is ready")

    def search(self, query: str, top_k: int = 3) -> List[Tuple[str, str]]:
        if self.vectorstore:
            try:
                retriever = self.vectorstore.as_retriever(search_kwargs={"k": top_k})
                docs = retriever.get_relevant_documents(query)
                return [
                    (getattr(doc, "metadata", {}).get("source", "unknown"), doc.page_content)
                    for doc in docs
                ]
            except Exception as exc:
                logger.warning("Vector retrieval failed, fallback to text search: %s", exc)

        hits: List[Tuple[str, int, str]] = []
        query_lower = query.lower()
        for doc in self.docs:
            text = doc.get("text", "")
            count = text.lower().count(query_lower)
            if count > 0:
                hits.append((doc.get("source", "unknown"), count, text[:1000]))
        hits.sort(key=lambda item: item[1], reverse=True)
        return [(item[0], item[2]) for item in hits[:top_k]]

    def check_abnormality(
        self,
        indicator: str,
        value: float,
        age_group: str = None,
        gender: str = None,
    ) -> Dict[str, Any]:
        try:
            numeric = float(value)
        except Exception:
            return {"is_abnormal": False, "level": "unknown", "detail": "non-numeric value"}

        ref = get_reference_range(indicator)
        if not ref:
            return {"is_abnormal": False, "level": "unknown", "detail": "missing reference range"}

        low = None
        high = None
        if gender and gender.lower().startswith("f") and isinstance(ref.get("female"), dict):
            low = ref.get("female", {}).get("min")
            high = ref.get("female", {}).get("max")
        elif gender and gender.lower().startswith("m") and isinstance(ref.get("male"), dict):
            low = ref.get("male", {}).get("min")
            high = ref.get("male", {}).get("max")
        elif isinstance(ref.get("normal"), dict):
            low = ref.get("normal", {}).get("min")
            high = ref.get("normal", {}).get("max")
        elif isinstance(ref.get("adult"), dict):
            low = ref.get("adult", {}).get("min")
            high = ref.get("adult", {}).get("max")

        is_abnormal = False
        level = "normal"
        detail = ""

        if low is not None and numeric < low:
            is_abnormal = True
            level = "low"
            detail = f"{indicator}={numeric} is below lower bound {low}"
        elif high is not None and numeric > high:
            is_abnormal = True
            crit_high = ref.get("critical_high")
            level = "critical" if crit_high is not None and numeric >= crit_high else "high"
            detail = f"{indicator}={numeric} is above upper bound {high}"

        return {
            "is_abnormal": is_abnormal,
            "level": level,
            "detail": detail,
            "value": numeric,
            "low": low,
            "high": high,
        }

    def analyze_lab_results(self, lab_results: Dict[str, float], gender: str = None) -> Dict[str, Any]:
        output = {"abnormalities": {}, "recommendations": []}
        for indicator, value in (lab_results or {}).items():
            result = self.check_abnormality(indicator, value, gender=gender)
            output["abnormalities"][indicator] = result
            if result.get("is_abnormal"):
                output["recommendations"].append(f"{indicator} abnormal: {result.get('detail')}")
        return output


class PatientHistoryEnhancer:
    def __init__(self, kb: Optional[KnowledgeBase]):
        self.kb = kb

    def enhance_medical_summary(self, history_text: str, lab_results: Dict[str, float]) -> str:
        if not history_text:
            history_text = ""
        if not self.kb or not lab_results:
            return history_text

        keys = list(lab_results.keys())[:3]
        query = history_text + "\nKey lab indicators: " + ",".join(keys)
        hits = self.kb.search(query, top_k=3)
        if not hits:
            return history_text

        snippets = [f"[{source}] {snippet[:400]}" for source, snippet in hits]
        return history_text + "\n[Knowledge Base Context]\n" + "\n".join(snippets)


def create_knowledge_base() -> KnowledgeBase:
    try:
        return KnowledgeBase()
    except Exception as exc:
        logger.warning("Failed to create KnowledgeBase, returning None: %s", exc)
        return None


__all__ = ["create_knowledge_base", "PatientHistoryEnhancer", "KnowledgeBase"]
