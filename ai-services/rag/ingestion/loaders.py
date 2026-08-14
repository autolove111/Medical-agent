"""
文档加载器

从 to_md/ 目录加载已清洗的 Markdown 文件，返回 LlamaIndex Document 列表。
"""

import logging
from pathlib import Path
from typing import List, Optional

from llama_index.core import Document
from llama_index.core import SimpleDirectoryReader

from rag.config import TO_MD_DIR

logger = logging.getLogger(__name__)


def load_documents_from_dir(
    dir_path: str | Path,
) -> List[Document]:
    """从目录加载 Markdown 文件。"""
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        logger.warning("Document directory not found: %s", dir_path)
        return []

    try:
        reader = SimpleDirectoryReader(
            input_dir=str(dir_path),
            recursive=True,
            required_exts=[".md"],
            filename_as_id=True,
        )
        documents = reader.load_data()
        logger.info("Loaded %d documents from %s", len(documents), dir_path)
        return documents
    except Exception as exc:
        logger.error("Failed to load documents from %s: %s", dir_path, exc)
        return []


def load_all_documents() -> List[Document]:
    """加载 to_md/ 目录下所有已清洗的 Markdown 文档。"""
    return load_documents_from_dir(TO_MD_DIR)
