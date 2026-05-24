from typing import Iterable, List, Optional, Sequence

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


DEFAULT_RECURSIVE_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    "，",
    " ",
    "",
]


def create_recursive_splitter(
    chunk_size: int,
    chunk_overlap: int,
    separators: Optional[Sequence[str]] = None,
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=list(separators or DEFAULT_RECURSIVE_SEPARATORS),
    )


def split_documents(
    documents: Iterable[Document],
    strategy: str = "recursive",
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[Document]:
    if strategy != "recursive":
        raise ValueError(f"Unsupported chunk strategy: {strategy}")

    splitter = create_recursive_splitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_documents(list(documents))
