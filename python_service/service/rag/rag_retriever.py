import logging
from typing import Optional

from core.config import settings
from service.rag.embedding import build_main_vectorstore, load_vectorstore_from_dir

logger = logging.getLogger(__name__)


class GlobalRetrieverRegistry:
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self.vectorstore = None
        self.retriever = None

    def _build_retriever(self, vectorstore):
        return vectorstore.as_retriever(search_kwargs={"k": getattr(settings, "RAG_TOP_K", 3)})

    def get_vectorstore(self):
        if self.vectorstore is not None:
            return self.vectorstore

        loaded = load_vectorstore_from_dir(settings.VECTOR_DB_PATH + "\\main", self.embeddings)
        if loaded is None:
            logger.info("Global vectorstore missing, building from source documents")
            loaded = build_main_vectorstore(self.embeddings)

        self.vectorstore = loaded
        return self.vectorstore

    def get_retriever(self) -> Optional[object]:
        if self.retriever is not None:
            return self.retriever

        vectorstore = self.get_vectorstore()
        if vectorstore is None:
            return None

        self.retriever = self._build_retriever(vectorstore)
        return self.retriever
