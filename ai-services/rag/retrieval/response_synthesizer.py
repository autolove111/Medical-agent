"""
结果格式化

将检索到的 NodeWithScore 列表格式化为可读的文本回答。
附带来源引用信息。
"""

import logging
from typing import Dict, List, Tuple

from llama_index.core.schema import NodeWithScore

logger = logging.getLogger(__name__)

MAX_NODE_LENGTH = 600  # 单个节点最大字符数


def _truncate_text(text: str, max_len: int = MAX_NODE_LENGTH) -> str:
    """截断过长文本，在句号或换行处断开。"""
    if len(text) <= max_len:
        return text

    truncated = text[:max_len]
    last_break = max(truncated.rfind("。"), truncated.rfind("\n"), truncated.rfind(". "))
    if last_break > max_len // 2:
        truncated = truncated[:last_break + 1]

    return truncated + "\n...(内容已截断)"


def format_nodes_as_answer(nodes: List[NodeWithScore]) -> str:
    """将 NodeWithScore 列表格式化为带来源引用的回答文本。"""
    if not nodes:
        return ""

    context_parts: List[str] = []
    for i, node in enumerate(nodes, 1):
        metadata = node.metadata or {}
        source = metadata.get("source", metadata.get("file_name", "unknown"))
        content = _truncate_text(node.get_content())

        score_str = f" (score: {node.score:.3f})" if node.score else ""
        context_parts.append(f"【来源{i}】{source}{score_str}\n{content}")

    return "\n\n".join(context_parts)


def extract_source_metadata(nodes: List[NodeWithScore]) -> List[Dict]:
    """从 NodeWithScore 列表中提取结构化来源元数据。"""
    sources: List[Dict] = []
    seen = set()

    for node in nodes:
        metadata = node.metadata or {}
        source_name = metadata.get("source", metadata.get("file_name", "unknown"))
        content = node.get_content() or ""

        # 提取章节（如果有 Markdown 标题）
        section = ""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("## ") or line.startswith("# "):
                section = line.lstrip("# ").strip()
                break

        # 去重
        key = f"{source_name}:{section}"
        if key in seen:
            continue
        seen.add(key)

        sources.append({
            "source": source_name,
            "section": section,
            "excerpt": content[:200].strip(),
            "score": node.score,
            "char_count": len(content),
        })

    return sources
