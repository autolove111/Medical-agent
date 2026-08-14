"""
递归标题感知分块（Recursive Heading-Aware Chunking）

策略：递归字符切分 + 标题作为最高优先级分隔符 + 标题链 metadata

分隔符优先级：
  \n# → \n## → \n### → \n#### → \n##### → \n###### → \n\n → 。→ ，→ ""

每个 chunk 携带所属的标题链（祖先链），如：
  "# 第二篇 呼吸系统疾病 > ## 第一章 总论 > ### 第一节 急性上呼吸道感染"

使用方式：
    from rag.ingestion.chunkers import chunk_documents
    nodes = chunk_documents(documents)
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from llama_index.core.schema import BaseNode, TextNode

from core.config import settings
from rag.config import NODE_MD_DIR

logger = logging.getLogger(__name__)

# 标题正则
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# 分隔符优先级：标题从细到粗，然后是段落、句子、字符
_SEPARATORS = [
    "\n###### ",
    "\n##### ",
    "\n#### ",
    "\n### ",
    "\n## ",
    "\n# ",
    "\n\n",
    "。",
    "，",
    "",
]


def _build_heading_map(text: str) -> List[dict]:
    """扫描全文，建立每个标题的位置和层级信息。

    Returns:
        [{"line_idx": 10, "level": 2, "heading": "## 第一章 总论", "title": "第一章 总论"}, ...]
    """
    lines = text.split("\n")
    headings = []
    for i, line in enumerate(lines):
        m = _RE_HEADING.match(line.strip())
        if m:
            headings.append({
                "line_idx": i,
                "level": len(m.group(1)),
                "heading": line.strip(),
                "title": m.group(2).strip(),
            })
    return headings


def _get_heading_chain(headings: List[dict], chunk_start_line: int) -> str:
    """根据 chunk 起始行号，找到该位置所属的标题祖先链。

    逻辑：找到 chunk_start_line 之前、level 最小的标题作为祖先，
    然后逐级找更深的标题。
    """
    # 找到 chunk 开始之前的所有标题
    preceding = [h for h in headings if h["line_idx"] <= chunk_start_line]
    if not preceding:
        return ""

    # 用栈维护祖先链：逐个处理标题，弹出同级或更深的
    stack = []
    for h in preceding:
        while stack and stack[-1]["level"] >= h["level"]:
            stack.pop()
        stack.append(h)

    return " > ".join(h["heading"] for h in stack)


def _find_line_number(full_text: str, offset: int) -> int:
    """根据字符偏移量计算行号。"""
    return full_text[:offset].count("\n")


def _recursive_split(
    text: str,
    separators: List[str],
    chunk_size: int,
    chunk_overlap: int,
) -> List[str]:
    """递归切分文本。

    Args:
        text: 待切分文本
        separators: 分隔符优先级列表
        chunk_size: 最大 chunk 字符数
        chunk_overlap: 相邻 chunk 重叠字符数

    Returns:
        切分后的文本列表
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    for i, sep in enumerate(separators):
        # 尝试用当前分隔符切分
        if sep == "":
            # 最后兜底：强制按字符切
            parts = []
            for start in range(0, len(text), chunk_size - chunk_overlap):
                end = min(start + chunk_size, len(text))
                parts.append(text[start:end])
                if end >= len(text):
                    break
            return [p for p in parts if p.strip()]

        parts = text.split(sep)
        if len(parts) <= 1:
            # 这个分隔符切不动，尝试下一个
            continue

        # 切开了，对每段递归处理
        result = []
        for part in parts:
            if not part.strip():
                continue

            if len(part) <= chunk_size:
                result.append(part)
            else:
                # 这段还是太大，用更低优先级的分隔符递归切
                sub_parts = _recursive_split(
                    part, separators[i + 1:], chunk_size, chunk_overlap
                )
                result.extend(sub_parts)

        # 合并相邻小 chunk（避免太碎）
        merged = _merge_small_chunks(result, chunk_size, min_size=chunk_size // 5)

        # 给相邻 chunk 加 overlap
        if chunk_overlap > 0 and len(merged) > 1:
            merged = _add_overlap(merged, chunk_overlap)

        return merged

    # 所有分隔符都切不动（理论上不会到这里）
    return [text]


def _merge_small_chunks(chunks: List[str], chunk_size: int, min_size: int) -> List[str]:
    """合并过小的相邻 chunk。"""
    if not chunks:
        return []

    merged = [chunks[0]]
    for chunk in chunks[1:]:
        if len(merged[-1]) < min_size and len(merged[-1]) + len(chunk) <= chunk_size:
            merged[-1] = merged[-1] + "\n" + chunk
        else:
            merged.append(chunk)
    return merged


def _add_overlap(chunks: List[str], overlap: int) -> List[str]:
    """给相邻 chunk 添加重叠。"""
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_tail = chunks[i - 1][-overlap:]
        result.append(prev_tail + "\n" + chunks[i])
    return result


def heading_aware_chunk(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[dict]:
    """递归标题感知切块。

    Args:
        text: Markdown 全文
        chunk_size: 最大 chunk 字符数
        chunk_overlap: 相邻 chunk 重叠字符数

    Returns:
        [{"text": "chunk文本", "heading": "标题链"}, ...]
    """
    if not text.strip():
        return []

    # 建立标题位置映射
    headings = _build_heading_map(text)

    # 递归切分
    raw_chunks = _recursive_split(text, _SEPARATORS, chunk_size, chunk_overlap)
    if not raw_chunks:
        return []

    # 给每个 chunk 找标题链
    chunks = []
    for chunk_text in raw_chunks:
        if not chunk_text.strip():
            continue

        # 找这个 chunk 在原文中的起始位置
        offset = text.find(chunk_text[:50])  # 用前50字符定位
        if offset == -1:
            offset = 0
        line_idx = _find_line_number(text, offset)

        heading_chain = _get_heading_chain(headings, line_idx)

        chunks.append({
            "text": chunk_text.strip(),
            "heading": heading_chain,
        })

    return chunks


def chunk_documents(documents, chunk_size: int = None, chunk_overlap: int = None) -> List[BaseNode]:
    """将文档列表切分为 Node 列表。

    Args:
        documents: LlamaIndex Document 列表
        chunk_size: 最大字符数，默认取 settings.CHUNK_SIZE
        chunk_overlap: 重叠字符数，默认取 settings.CHUNK_OVERLAP

    Returns:
        TextNode 列表，每个 node 的 metadata 包含 heading 信息
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    all_nodes: List[BaseNode] = []

    for doc in documents:
        text = doc.text or ""
        if not text.strip():
            continue

        chunks = heading_aware_chunk(text, chunk_size, chunk_overlap)

        for i, chunk in enumerate(chunks):
            node = TextNode(
                text=chunk["text"],
                metadata={
                    **(doc.metadata or {}),
                    "heading": chunk["heading"],
                    "chunk_index": i,
                },
            )
            all_nodes.append(node)

    logger.info(
        "Recursive heading-aware chunking | docs=%d -> nodes=%d (size=%d overlap=%d)",
        len(documents),
        len(all_nodes),
        chunk_size,
        chunk_overlap,
    )
    return all_nodes


def save_nodes_to_files(
    documents,
    output_dir: Optional[Path] = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> int:
    """将每个文档的 node 保存为独立的 md 文件，方便人工检查。

    输出结构：
        node_md/
        ├── 内科学_nodes.md
        ├── 肾脏病学_nodes.md
        └── ...

    Args:
        documents: Document 列表
        output_dir: 输出目录，默认 NODE_MD_DIR
        chunk_size: 分块大小
        chunk_overlap: 分块重叠

    Returns:
        保存的文件数
    """
    output_dir = Path(output_dir) if output_dir else NODE_MD_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    saved = 0
    global_index = 0

    for doc in documents:
        file_name = doc.metadata.get("file_name", "unknown.md")
        stem = Path(file_name).stem
        out_path = output_dir / f"{stem}_nodes.md"

        text = doc.text or ""
        if not text.strip():
            continue

        chunks = heading_aware_chunk(text, chunk_size, chunk_overlap)
        if not chunks:
            continue

        parts = []
        for chunk in chunks:
            parts.append(f"---\n[Node #{global_index}] heading: {chunk['heading']} | len: {len(chunk['text'])}\n---")
            parts.append(chunk["text"])
            parts.append("")
            global_index += 1

        out_path.write_text("\n".join(parts), encoding="utf-8")
        saved += 1
        logger.info("Saved nodes: %s (%d nodes)", out_path.name, len(chunks))

    logger.info("All nodes saved | files=%d dir=%s", saved, output_dir)
    return saved
