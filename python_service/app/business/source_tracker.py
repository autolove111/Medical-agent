"""
来源追踪器：追踪每条医学建议对应的知识库来源

核心职责：
- 从 RAG 检索结果中提取结构化来源信息
- 按建议类型（指标解读 / 联动分析 / 饮食建议 / 运动建议）分类追踪
- 生成可注入 prompt 的来源引用块
- 生成前端可渲染的来源列表
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Citation:
    """单条知识来源引用"""
    source_name: str                 # 文档名，如 "肾脏医学指南.txt"
    excerpt: str = ""                # 原文片段（前 200 字符）
    section: str = ""                # 章节名（如有）
    indicator_keys: list[str] = field(default_factory=list)  # 关联的指标
    category: str = ""               # indicator / correlation / diet / exercise


@dataclass
class SourceTracker:
    """来源追踪器：收集并管理所有引用"""

    citations: list[Citation] = field(default_factory=list)

    def add_from_rag_docs(self, docs: list, category: str = "", indicator_keys: list[str] | None = None) -> int:
        """
        从 RAG 返回的 Document 列表中提取引用

        参数：
            docs:     langchain Document 列表
            category: 引用类别（indicator/correlation/diet/exercise）
            indicator_keys: 关联的指标 key 列表

        返回：添加的引用数量
        """
        if indicator_keys is None:
            indicator_keys = []

        added = 0
        for doc in docs:
            metadata = getattr(doc, "metadata", {}) or {}
            source_name = metadata.get("source", "unknown")
            page_content = getattr(doc, "page_content", "") or ""

            # 尝试提取章节名（如 "## 慢性肾脏病饮食管理"）
            section = ""
            for line in page_content.split("\n"):
                line = line.strip()
                if line.startswith("## ") or line.startswith("# "):
                    section = line.lstrip("# ").strip()
                    break

            excerpt = page_content[:200].strip()

            # 去重（同源同章节不重复添加）
            if not any(c.source_name == source_name and c.section == section for c in self.citations):
                self.citations.append(Citation(
                    source_name=source_name,
                    excerpt=excerpt,
                    section=section,
                    indicator_keys=list(indicator_keys),
                    category=category,
                ))
                added += 1

        return added

    def add_manual(self, source_name: str, excerpt: str, category: str = "", indicator_keys: list[str] | None = None):
        """手动添加一条引用（用于内置规则来源）"""
        self.citations.append(Citation(
            source_name=source_name,
            excerpt=excerpt,
            category=category,
            indicator_keys=indicator_keys or [],
        ))

    def get_by_category(self, category: str) -> list[Citation]:
        return [c for c in self.citations if c.category == category]

    def get_by_indicator(self, key: str) -> list[Citation]:
        return [c for c in self.citations if key in c.indicator_keys]

    def to_prompt_block(self) -> str:
        """
        生成注入 prompt 的来源引用块

        格式：
        【知识库来源引用】
        1. [肾脏医学指南.txt] §慢性肾脏病饮食管理
           肌酐是肾功能主要标志...
        2. [营养学指南.txt] §肾病饮食原则
           慢性肾脏病患者应限制蛋白质摄入...
        """
        if not self.citations:
            return ""

        lines = ["【知识库来源引用】以下为本次解读引用的知识来源："]
        for i, c in enumerate(self.citations, 1):
            header = f"[{c.source_name}]"
            if c.section:
                header += f" §{c.section}"
            lines.append(f"{i}. {header}")
            if c.excerpt:
                lines.append(f"   {c.excerpt[:120]}")

        return "\n".join(lines)

    def to_api_list(self) -> list[dict]:
        """生成前端可渲染的来源列表"""
        return [
            {
                "source": c.source_name,
                "section": c.section,
                "excerpt": c.excerpt,
                "category": c.category,
                "indicators": c.indicator_keys,
            }
            for c in self.citations
        ]

    @property
    def source_count(self) -> int:
        return len(self.citations)

    @property
    def unique_sources(self) -> list[str]:
        return list(dict.fromkeys(c.source_name for c in self.citations))
