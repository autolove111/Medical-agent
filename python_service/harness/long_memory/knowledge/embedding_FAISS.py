import logging
import os
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from core.config import settings
from knowledge.chunk_strategies import split_documents
from knowledge.document_loaders import (
    load_text_documents,
    load_all_knowledge_documents,
    resolve_medical_docs_dir,
)
from knowledge.text_cleaner import clean_documents

logger = logging.getLogger(__name__)
DEFAULT_EMBEDDING_MODEL_ID = "maidalun1020/bce-embedding-base_v1"


def resolve_embedding_model_source() -> str:
    configured_source = os.getenv(
        "RAG_LOCAL_EMBEDDING_PATH",
        settings.RAG_LOCAL_EMBEDDING_PATH or DEFAULT_EMBEDDING_MODEL_ID,
    )

    # 相对路径基于 python_service/ 目录解析（与 .env 同目录）
    if not os.path.isabs(configured_source):
        _env_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        configured_source = os.path.normpath(os.path.join(_env_dir, configured_source))

    if os.path.isdir(configured_source):
        return configured_source

    if configured_source.startswith("/"):
        logger.warning(
            "Local embedding path not found: %s, falling back to %s",
            configured_source,
            DEFAULT_EMBEDDING_MODEL_ID,
        )
        return DEFAULT_EMBEDDING_MODEL_ID

    return configured_source


class BCEFlagEmbedding(Embeddings):
    """LangChain adapter around a local SentenceTransformer model."""

    def __init__(self, model_path: Optional[str] = None, use_fp16: bool = False):
        resolved_path = model_path or resolve_embedding_model_source()
        self.model_path = resolved_path
        self.use_fp16 = use_fp16
        self.model = None
        self.tokenizer = None
        self.backend = "sentence-transformers"
        configured_device = (settings.RAG_EMBEDDING_DEVICE or "cpu").strip().lower()
        if configured_device == "cuda" and not torch.cuda.is_available():
            logger.warning("RAG_EMBEDDING_DEVICE=cuda but CUDA is unavailable; falling back to CPU")
            configured_device = "cpu"
        self.device = configured_device
        self.dtype = torch.float16 if use_fp16 and self.device == "cuda" else torch.float32

        try:
            self.model = SentenceTransformer(resolved_path, device=self.device)
        except Exception as exc:
            logger.warning(
                "SentenceTransformer load failed for %s, falling back to raw transformers: %s",
                resolved_path,
                exc,
            )
            self.backend = "transformers"
            self.tokenizer = AutoTokenizer.from_pretrained(
                resolved_path,
                local_files_only=os.path.isdir(resolved_path),
                trust_remote_code=True,
            )
            self.model = AutoModel.from_pretrained(
                resolved_path,
                local_files_only=os.path.isdir(resolved_path),
                trust_remote_code=True,
                torch_dtype=self.dtype,
            )
            self.model.to(self.device)
            self.model.eval()

    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, dim=1) / torch.clamp(
            input_mask_expanded.sum(dim=1),
            min=1e-9,
        )

    def _encode_with_transformers(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}

        with torch.no_grad():
            model_output = self.model(**encoded)
            sentence_embeddings = self._mean_pooling(model_output, encoded["attention_mask"])
            sentence_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)

        return sentence_embeddings.detach().cpu().tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.backend == "sentence-transformers":
            return self.model.encode(texts, convert_to_numpy=True).tolist()
        return self._encode_with_transformers(texts)

    def embed_query(self, text: str) -> List[float]:
        if self.backend == "sentence-transformers":
            return self.model.encode([text], convert_to_numpy=True)[0].tolist()
        return self._encode_with_transformers([text])[0]


def create_embeddings(
    purpose: str = "default",
) -> BCEFlagEmbedding:
    _ = purpose
    local_path = resolve_embedding_model_source()
    logger.info("RAG using local SentenceTransformer model: %s", local_path)
    return BCEFlagEmbedding(model_path=local_path, use_fp16=False)


def resolve_vectorstore_dir(scope_key: str = "main", base_path: Optional[str] = None) -> str:
    root = base_path or settings.VECTOR_DB_PATH
    _ = scope_key
    return os.path.join(root, "main")


def load_vectorstore_from_dir(vector_db_path: str, embeddings) -> Optional[FAISS]:
    index_path = os.path.join(vector_db_path, "index.faiss")
    if not os.path.exists(index_path):
        return None

    try:
        return FAISS.load_local(
            vector_db_path,
            embeddings,
            allow_dangerous_deserialization=True,
        )
    except Exception as exc:
        logger.warning("Failed to load vectorstore from %s: %s", vector_db_path, exc)
        return None


def load_documents_for_source(source_path: str) -> List[Document]:
    raw_documents = load_text_documents(source_path)
    return clean_documents(raw_documents)


def load_default_medical_documents() -> List[Document]:
    medical_dir = resolve_medical_docs_dir()
    if not medical_dir:
        return []
    return load_documents_for_source(medical_dir)


def build_vectorstore_from_documents(
    embeddings,
    documents: List[Document],
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    batch_size: int = 100,
) -> Optional[FAISS]:
    if not documents:
        return None

    chunks = split_documents(
        documents,
        strategy="recursive",
        chunk_size=chunk_size or getattr(settings, "CHUNK_SIZE", 500),
        chunk_overlap=chunk_overlap or getattr(settings, "CHUNK_OVERLAP", 50),
    )
    if not chunks:
        return None

    vectorstore = FAISS.from_documents(chunks[:batch_size], embeddings)
    for idx in range(batch_size, len(chunks), batch_size):
        vectorstore.add_documents(chunks[idx:idx + batch_size])
    return vectorstore


def build_main_vectorstore(embeddings) -> Optional[FAISS]:
    return build_global_vectorstore(embeddings)


def build_global_vectorstore(embeddings) -> Optional[FAISS]:
    documents = clean_documents(load_all_knowledge_documents())
    vectorstore = build_vectorstore_from_documents(
        embeddings,
        documents,
        chunk_size=getattr(settings, "CHUNK_SIZE", 500),
        chunk_overlap=getattr(settings, "CHUNK_OVERLAP", 50),
    )
    if vectorstore is None:
        logger.warning("No chunks generated for global knowledge documents")
        return None

    vector_db_path = resolve_vectorstore_dir("main")
    os.makedirs(vector_db_path, exist_ok=True)
    vectorstore.save_local(vector_db_path)
    logger.info("Saved global vectorstore | path=%s", vector_db_path)
    return vectorstore
