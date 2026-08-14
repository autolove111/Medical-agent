"""
Markdown 文档清洗

针对 PDF 提取后的医学文档，清理 HTML 标签残留：
1. <table> → Markdown 表格（处理 rowspan/colspan）
2. <details><summary>xxx</summary>...</details> → 解开保留内容
3. <br>、<sup> 等残留标签 → 清除

使用方式：
    from rag.ingestion.cleaners import clean_markdown
    cleaned = clean_markdown(raw_text)
"""

import re

# ============================================================
# 预编译正则
# ============================================================

_RE_HTML_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_RE_HTML_SUP = re.compile(r"</?sup>", re.IGNORECASE)
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


# ============================================================
# <table> → Markdown 表格
# ============================================================

def _html_table_to_markdown(html: str) -> str:
    """将单个 <table> HTML 块转换为 Markdown 表格，处理 rowspan/colspan。"""
    from html.parser import HTMLParser

    class _TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.grid: list[list[str]] = []
            self.row = 0
            self.col = 0
            self._cell_text = ""
            self._in_cell = False

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.grid.append([])
                self.col = 0
            elif tag in ("td", "th"):
                self._in_cell = True
                self._cell_text = ""
                row = self.grid[-1]
                while len(row) > self.col and row[self.col] is not None:
                    self.col += 1
                attrs_dict = dict(attrs)
                rowspan = int(attrs_dict.get("rowspan", 1))
                colspan = int(attrs_dict.get("colspan", 1))
                for dr in range(rowspan):
                    for dc in range(colspan):
                        r = self.row + dr
                        c = self.col + dc
                        while len(self.grid) <= r:
                            self.grid.append([])
                        while len(self.grid[r]) <= c:
                            self.grid[r].append(None)

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self._in_cell:
                self._in_cell = False
                text = self._cell_text.strip().replace("|", "\\|").replace("\n", " ")
                if self.grid and self.grid[-1]:
                    self.grid[-1][self.col] = text
                self.col += 1
            elif tag == "tr":
                self.row += 1

        def handle_data(self, data):
            if self._in_cell:
                self._cell_text += data

    parser = _TableParser()
    try:
        parser.feed(html)
    except Exception:
        return html

    if not parser.grid:
        return html

    max_cols = max(len(row) for row in parser.grid)
    for row in parser.grid:
        while len(row) < max_cols:
            row.append("")

    lines = []
    for i, row in enumerate(parser.grid):
        cells = [c if c is not None else "" for c in row]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")

    return "\n".join(lines)


# ============================================================
# 主清洗函数
# ============================================================

def clean_markdown(text: str) -> str:
    """对 Markdown 文本执行清洗，去除 PDF 提取残留的 HTML 标签。

    Args:
        text: 原始 Markdown 文本

    Returns:
        清洗后的 Markdown 文本
    """
    # 1. <table> → Markdown 表格
    text = re.sub(
        r"<table>.*?</table>",
        lambda m: _html_table_to_markdown(m.group(0)),
        text,
        flags=re.DOTALL,
    )

    # 2. <details><summary>xxx</summary> ... </details> → 保留内部内容
    text = re.sub(
        r"<details>\s*<summary>[^<]*</summary>\s*(.*?)\s*</details>",
        r"\1",
        text,
        flags=re.DOTALL,
    )

    # 3. 残留 HTML 标签
    text = _RE_HTML_BR.sub("\n", text)
    text = _RE_HTML_SUP.sub("", text)
    text = _RE_HTML_COMMENT.sub("", text)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)

    # 4. 多余空行
    text = _RE_EXCESS_BLANK_LINES.sub("\n\n", text)

    return text.strip()
