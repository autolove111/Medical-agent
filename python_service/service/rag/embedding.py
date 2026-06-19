import logging
import os
import time
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from core.config import settings
from service.rag.chunk_strategies import split_documents
from service.rag.document_loaders import (
    load_text_documents,
    load_all_knowledge_documents,
    resolve_medical_docs_dir,
)
from service.rag.text_cleaner import clean_documents

logger = logging.getLogger(__name__)
DEFAULT_EMBEDDING_MODEL_ID = "qihoo360/Zhinao-ChineseModernBert-Embedding"


# ============================================================
# OpenAI 兼容 Embedding API 适配器
# ============================================================

class OpenAICompatibleEmbedding(Embeddings):
    """通过 OpenAI 兼容 API（如 OpenAI / 硅基流动 / 本地 vLLM 等）获取 Embedding。

    实现 LangChain Embeddings 接口，直接对接 FAISS / Chroma 等向量库。

    使用方式：
        emb = OpenAICompatibleEmbedding(
            api_url="https://api.openai.com/v1/embeddings",
            api_key="sk-xxx",
            model_name="text-embedding-3-small",
        )
        vec = emb.embed_query("hello")
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model_name: str = "text-embedding-3-small",
        timeout: int = 30,
        dimensions: Optional[int] = None,
        max_retries: int = 3,
    ):
        import requests as _requests

        self._requests = _requests
        self.api_url = (api_url or settings.RAG_EMBEDDING_API_URL).rstrip("/")
        self.api_key = api_key or settings.RAG_EMBEDDING_API_KEY
        self.model_name = model_name or settings.RAG_EMBEDDING_MODEL_NAME
        self.timeout = timeout or settings.RAG_EMBEDDING_API_TIMEOUT
        self.dimensions = dimensions
        self.max_retries = max_retries

        logger.info(
            "OpenAICompatibleEmbedding initialized | url=%s model=%s",
            self.api_url,
            self.model_name,
        )

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 OpenAI 兼容 Embedding API，含重试逻辑。"""
        if not texts:
            return []

        payload: dict = {
            "model": self.model_name,
            "input": texts,
        }
        if self.dimensions:
            payload["dimensions"] = self.dimensions

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._requests.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                return [data["data"][i]["embedding"] for i in range(len(texts))]

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Embedding API call failed (attempt %d/%d): %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 10))

        raise RuntimeError(
            f"Embedding API call failed after {self.max_retries} attempts: {last_error}"
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._call_api(texts)

    def embed_query(self, text: str) -> List[float]:
        result = self._call_api([text])
        return result[0] if result else []


# ============================================================
# 本地 Embedding 模型（BCE-embedding / SentenceTransformer）
# ============================================================


def _download_from_modelscope(model_id: str, cache_dir: str) -> str:
    """从 ModelScope 下载模型，返回本地路径。

    自动将 HuggingFace 命名空间映射到 ModelScope：
      qihoo360/Zhinao-ChineseModernBert-Embedding → ZhipuAI/Zhinao-ChineseModernBert-Embedding
    """
    try:
        from modelscope import snapshot_download
        parts = model_id.split("/")
        if len(parts) == 2:
            org, repo = parts
            mapping = {
                "qihoo360": "ZhipuAI",
            }
            ms_id = f"{mapping.get(org, org)}/{repo}"
        else:
            ms_id = model_id
        local = snapshot_download(ms_id, cache_dir=cache_dir)
        logger.info("Downloaded from ModelScope: %s -> %s", ms_id, local)
        return local
    except ImportError:
        logger.warning("modelscope not installed, cannot auto-download from ModelScope")
        raise
    except Exception as exc:
        logger.warning("ModelScope download failed for %s: %s", model_id, exc)
        raise

def resolve_embedding_model_source() -> str:
    configured_source = os.getenv(
        "RAG_LOCAL_EMBEDDING_PATH",
        settings.RAG_LOCAL_EMBEDDING_PATH or DEFAULT_EMBEDDING_MODEL_ID,
    )

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
    """LangChain adapter around a local SentenceTransformer model.\n    Supports BCE-embedding, Zhinao-ChineseModernBert-Embedding, etc."""

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


# ============================================================
# Embedding 工厂函数
# ============================================================

def create_embeddings(
    purpose: str = "default",
) -> Embeddings:
    """创建 Embedding 实例，根据 RAG_USE_LOCAL_EMBEDDING 自动选择本地或 API。

    - 本地模式 (RAG_USE_LOCAL_EMBEDDING=true):  加载 BCE-embedding 等本地模型
    - API  模式 (RAG_USE_LOCAL_EMBEDDING=false): 调用 OpenAI 兼容 Embedding API
    """
    _ = purpose

    if not settings.RAG_USE_LOCAL_EMBEDDING:
        logger.info("RAG using OpenAI-compatible Embedding API")
        return OpenAICompatibleEmbedding()

    local_path = resolve_embedding_model_source()
    logger.info("RAG using local SentenceTransformer model: %s", local_path)
    return BCEFlagEmbedding(model_path=local_path, use_fp16=False)


# ============================================================
# 向量库构建工具
# ============================================================

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
