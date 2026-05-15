import logging
import re
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from knowledge.medical_knowledge import PatientHistoryEnhancer, create_knowledge_base
from knowledge.rag import retrieve_medical_knowledge
from llm.local_transformers import LocalTransformersChatModel
from tools.history import query_user_medical_history, set_current_user_id
from vision.vision_analyzer import (
    analyze_medical_image,
    analyze_medical_image_comprehensive,
    extract_patient_labs_from_ocr,
)

logger = logging.getLogger(__name__)

META_PATTERN = re.compile(r"\[META\|([^\]]+)\]")

BASE_SYSTEM_PROMPT = """You are a medical AI agent working in a single specialty lane.

Rules:
1. Answer in the user's language.
2. Use the user's question, OCR text, structured labs, history, and shared RAG context.
3. Stay inside your specialty. If the case is unclear, say what is uncertain.
4. Do not invent lab values, diagnoses, or history.
5. Do not claim a final clinical diagnosis.
6. End your answer with exactly one metadata line:
[META|medical:true/false|disease:name-or-None|allergy:name-or-None]
"""


class BaseMedicalAgent:
    agent_type = "general"
    agent_label = "General Agent"
    department_name: Optional[str] = None
    specialty_prompt = "Provide a clear and safe answer."

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.llm = LocalTransformersChatModel()
        self.streaming_llm = self.llm
        self.kb = None
        self.enhancer = None
        try:
            self.kb = create_knowledge_base()
            if self.kb:
                self.enhancer = PatientHistoryEnhancer(self.kb)
        except Exception as exc:
            logger.warning("Knowledge helper init failed for %s: %s", self.agent_type, exc)

    def build_memory_context(
        self,
        history_text: str,
        lab_results: Dict[str, float],
        query: str,
    ) -> str:
        focused_labs = self._format_lab_results(lab_results)
        parts: List[str] = []
        if history_text:
            parts.append(history_text)
        if focused_labs:
            parts.append("Structured labs:\n" + focused_labs)
        if query:
            parts.append("Current query:\n" + query)
        return "\n\n".join(parts) if parts else "No memory context."

    def get_system_prompt(self) -> str:
        dept = self.department_name or "General"
        return f"{BASE_SYSTEM_PROMPT}\n\nSpecialty: {dept}\n{self.specialty_prompt}"

    def build_user_prompt(
        self,
        query: str,
        ocr_text: str,
        rag_text: str,
        memory_text: str,
        lab_results: Dict[str, float],
    ) -> str:
        return (
            f"Agent type: {self.agent_type}\n"
            f"Department: {self.department_name or 'General'}\n\n"
            f"User question:\n{query}\n\n"
            f"OCR result:\n{ocr_text or 'None'}\n\n"
            f"Memory context:\n{memory_text or 'None'}\n\n"
            f"Structured labs:\n{self._format_lab_results(lab_results) or 'None'}\n\n"
            f"Shared RAG context:\n{rag_text or 'None'}\n"
        )

    def resolve_rag_context(self, query: str) -> Tuple[str, list]:
        return retrieve_medical_knowledge(query)

    def _build_messages(
        self,
        query: str,
        user_context: Optional[str] = None,
        lab_results: Optional[Dict] = None,
    ) -> Tuple[list, list]:
        set_current_user_id(self.user_id)

        query = (query or "").strip()
        merged_labs = dict(lab_results or {})
        cleaned_query = query
        ocr_text = ""

        image_url_raw = self._extract_image_url(query)
        image_url = self._normalize_image_url(image_url_raw) if image_url_raw else None
        if image_url_raw:
            cleaned_query = self._remove_image_url(query, image_url_raw)

        if image_url:
            try:
                ocr_text, extracted_labs = analyze_medical_image_comprehensive(image_url)
            except Exception as exc:
                logger.warning("OCR comprehensive path failed: %s", exc)
                ocr_text = analyze_medical_image(image_url)
                extracted_labs = extract_patient_labs_from_ocr(image_url)
            if extracted_labs:
                merged_labs.update(extracted_labs)

        rag_parts: List[str] = [cleaned_query]
        if ocr_text:
            rag_parts.append(ocr_text)
        if merged_labs:
            rag_parts.append(self._format_lab_results(merged_labs))
        rag_query = "\n".join(part for part in rag_parts if part)

        rag_text, sources = self.resolve_rag_context(rag_query)
        history_text = user_context or query_user_medical_history(self.user_id)
        if self.enhancer and merged_labs:
            try:
                history_text = self.enhancer.enhance_medical_summary(history_text, merged_labs)
            except Exception as exc:
                logger.warning("History enhancement failed for %s: %s", self.agent_type, exc)

        memory_text = self.build_memory_context(history_text or "", merged_labs, cleaned_query)
        user_prompt = self.build_user_prompt(
            query=cleaned_query or query,
            ocr_text=ocr_text,
            rag_text=rag_text,
            memory_text=memory_text,
            lab_results=merged_labs,
        )

        messages = [
            SystemMessage(content=self.get_system_prompt()),
            HumanMessage(content=user_prompt),
        ]
        return messages, sources

    def process_query(
        self,
        query: str,
        user_context: Optional[str] = None,
        lab_results: Optional[Dict] = None,
    ):
        try:
            messages, sources = self._build_messages(query, user_context, lab_results)
            response = self.llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            cleaned, _ = self.extract_metadata(content)
            return cleaned, sources
        except Exception as exc:
            logger.error("Process query failed for %s: %s", self.agent_type, exc, exc_info=True)
            return f"Processing error: {exc}", []

    def stream_query(
        self,
        query: str,
        user_context: Optional[str] = None,
        lab_results: Optional[Dict] = None,
    ) -> Iterator[Dict]:
        try:
            messages, sources = self._build_messages(query, user_context, lab_results)
            full_text = ""
            for chunk in self.streaming_llm.stream(messages):
                text = chunk.content if hasattr(chunk, "content") else ""
                if not text:
                    continue
                full_text += text
                yield {"type": "delta", "content": text}

            _, metadata = self.extract_metadata(full_text)
            formatted_sources = [
                {"content": source.page_content[:200], "metadata": getattr(source, "metadata", {})}
                for source in sources
            ]
            yield {
                "type": "meta",
                "metadata": metadata,
                "sources": formatted_sources,
            }
        except Exception as exc:
            logger.error("Stream query failed for %s: %s", self.agent_type, exc, exc_info=True)
            yield {"type": "error", "error": str(exc)}

    def extract_metadata(self, text: str) -> Tuple[str, Dict]:
        metadata = {
            "isMedical": False,
            "diseases": "",
            "drugAllergies": "",
        }
        match = META_PATTERN.search(text or "")
        if not match:
            return text, metadata

        parsed: Dict[str, str] = {}
        for field in match.group(1).split("|"):
            if ":" not in field:
                continue
            key, value = field.split(":", 1)
            parsed[key.strip().lower()] = value.strip()

        metadata["isMedical"] = parsed.get("medical", "false").lower() == "true"
        disease = parsed.get("disease", "None")
        allergy = parsed.get("allergy", "None")
        metadata["diseases"] = "" if disease == "None" else disease
        metadata["drugAllergies"] = "" if allergy == "None" else allergy
        cleaned = META_PATTERN.sub("", text).rstrip()
        return cleaned, metadata

    def _format_lab_results(self, lab_results: Dict[str, float]) -> str:
        if not lab_results:
            return ""
        return "\n".join(f"- {key}: {value}" for key, value in sorted(lab_results.items()))

    def _extract_image_url(self, text: str) -> Optional[str]:
        candidates = re.findall(r"https?://[^\s\]\)\}]+", text or "", flags=re.IGNORECASE)
        for url in candidates:
            cleaned = self._trim_url_punctuation(url)
            if "/api/v1/file/view/" in cleaned:
                return cleaned
            if re.search(r"\.(png|jpg|jpeg|gif|webp|bmp)(?:\?.*)?$", cleaned, re.IGNORECASE):
                return cleaned
        return None

    def _trim_url_punctuation(self, url: str) -> str:
        return url.rstrip("，。；;!！?)）]\"'")

    def _normalize_image_url(self, url: str) -> str:
        try:
            parsed = urlsplit(url)
            encoded_path = quote(parsed.path, safe="/%")
            encoded_query = quote(parsed.query, safe="=&%")
            return urlunsplit(
                (parsed.scheme, parsed.netloc, encoded_path, encoded_query, parsed.fragment)
            )
        except Exception:
            return url

    def _remove_image_url(self, text: str, image_url: str) -> str:
        compact = (text or "").replace(image_url, "").strip()
        return compact or "Please analyze the recognized report content."
