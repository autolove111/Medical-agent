import os
from typing import Iterable, List, Tuple

from langchain_community.document_loaders import (
    DirectoryLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MAIN_DOCS_DIR = os.path.join(BASE_DIR, "main_agent_docs")
DEPT_DOCS_DIR = os.path.join(BASE_DIR, "dept_agent_docs")
MEDICAL_DOCS_DIR = os.path.join(BASE_DIR, "medical_docs")

TEXT_GLOB = "*.[tT][xX][tT]"
MD_GLOB = "*.[mM][dD]"
PDF_GLOB = "*.[pP][dD][fF]"
DOCX_GLOB = "*.[dD][oO][cC][xX]"

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def is_supported_document_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS


def iter_supported_document_files(source_dir: str) -> List[str]:
    if not os.path.isdir(source_dir):
        return []

    files: List[str] = []
    for root, _, names in os.walk(source_dir):
        for name in sorted(names):
            full_path = os.path.join(root, name)
            if is_supported_document_file(full_path):
                files.append(full_path)
    return files


def _load_directory(
    source_path: str,
    glob: str,
    loader_cls,
    loader_kwargs: dict | None = None,
) -> List[Document]:
    loader = DirectoryLoader(
        source_path,
        glob=glob,
        loader_cls=loader_cls,
        loader_kwargs=loader_kwargs or {},
        show_progress=False,
        silent_errors=True,
    )
    return loader.load()


def _load_single_file(source_path: str, encoding: str = "utf-8") -> List[Document]:
    extension = os.path.splitext(source_path)[1].lower()

    if extension in {".txt", ".md"}:
        return TextLoader(source_path, encoding=encoding).load()
    if extension == ".pdf":
        return PyPDFLoader(source_path).load()
    if extension == ".docx":
        return Docx2txtLoader(source_path).load()

    return []


def load_text_documents(source_path: str, encoding: str = "utf-8") -> List[Document]:
    """Load supported knowledge-base documents from a file or directory."""
    if not source_path or not os.path.exists(source_path):
        return []

    if os.path.isdir(source_path):
        documents: List[Document] = []
        documents.extend(
            _load_directory(
                source_path,
                TEXT_GLOB,
                TextLoader,
                {"encoding": encoding},
            )
        )
        documents.extend(
            _load_directory(
                source_path,
                MD_GLOB,
                TextLoader,
                {"encoding": encoding},
            )
        )
        documents.extend(_load_directory(source_path, PDF_GLOB, PyPDFLoader))
        documents.extend(_load_directory(source_path, DOCX_GLOB, Docx2txtLoader))
        return documents

    return _load_single_file(source_path, encoding=encoding)


def iter_department_sources() -> List[Tuple[str, str]]:
    """Return all supported department knowledge files."""
    if not os.path.isdir(DEPT_DOCS_DIR):
        return []

    items: List[Tuple[str, str]] = []
    for name in sorted(os.listdir(DEPT_DOCS_DIR)):
        path = os.path.join(DEPT_DOCS_DIR, name)
        if not os.path.isfile(path) or not is_supported_document_file(path):
            continue
        items.append((os.path.splitext(name)[0], path))
    return items


def load_main_corpus() -> List[Document]:
    return load_text_documents(MAIN_DOCS_DIR)


def load_all_dept_docs() -> List[Document]:
    documents: List[Document] = []
    for _, file_path in iter_department_sources():
        documents.extend(load_text_documents(file_path))
    return documents


def load_all_knowledge_documents() -> List[Document]:
    documents: List[Document] = []
    documents.extend(load_text_documents(MAIN_DOCS_DIR))
    documents.extend(load_text_documents(DEPT_DOCS_DIR))
    # medical_docs 目录不存在，跳过加载
    if os.path.exists(MEDICAL_DOCS_DIR):
        documents.extend(load_text_documents(MEDICAL_DOCS_DIR))
    return documents


def load_medical_corpus() -> List[Document]:
    return load_text_documents(MEDICAL_DOCS_DIR)


def resolve_main_corpus_dir() -> str | None:
    return MAIN_DOCS_DIR if os.path.exists(MAIN_DOCS_DIR) else None


def resolve_medical_docs_dir() -> str | None:
    return MEDICAL_DOCS_DIR if os.path.exists(MEDICAL_DOCS_DIR) else None
