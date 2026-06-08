import re
from typing import Iterable, List
from langchain_core.documents import Document

# ===================== 预定义正则表达式（文本清洗专用） =====================
# 匹配ASCII控制字符（不可见、无用字符）
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# 匹配行尾多余空格/制表符
_TRAILING_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)
# 匹配3个及以上连续空行，用于压缩多余空行
_EXCESSIVE_BLANK_LINES_RE = re.compile(r"\n{3,}")

# ===================== 文本清洗核心函数 =====================
def clean_text(text: str) -> str:
    """
    核心文本清洗函数：清除文本中的无用字符、规范格式、压缩空白
    :param text: 原始文本字符串
    :return: 清洗后的干净文本
    """
    # 空文本直接返回空字符串
    if not text:
        return ""

    # 1. 移除UTF-8 BOM头（Windows文件常见乱码字符）
    cleaned = text.replace("\ufeff", "")
    # 2. 统一换行符：将\r\n、\r 全部规范为\n
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    # 3. 移除所有ASCII控制字符（不可见无用字符）
    cleaned = _CONTROL_CHAR_RE.sub("", cleaned)
    # 4. 全角空格 → 半角空格（统一格式）
    cleaned = cleaned.replace("\u3000", " ")
    # 5. 移除每一行末尾的多余空格/制表符
    cleaned = _TRAILING_SPACE_RE.sub("\n", cleaned)
    # 6. 压缩连续空行：3个及以上空行 → 保留2个空行
    cleaned = _EXCESSIVE_BLANK_LINES_RE.sub("\n\n", cleaned)
    
    # 7. 去除文本首尾的所有空白字符，返回最终结果
    return cleaned.strip()


def clean_document(document: Document) -> Document:
    """
    清洗 单个LangChain Document 对象
    :param document: 原始Document（含page_content和metadata）
    :return: 文本内容清洗后的新Document（元数据保持不变）
    """
    # 安全获取元数据，避免元数据为空时报错
    metadata = dict(getattr(document, "metadata", {}) or {})
    # 清洗文本内容，返回新的Document对象
    return Document(page_content=clean_text(document.page_content), metadata=metadata)


def clean_documents(documents: Iterable[Document]) -> List[Document]:
    """
    批量清洗 多个LangChain Document 对象
    自动过滤掉【清洗后为空】的无效文档
    :param documents: 可迭代的Document列表/集合
    :return: 清洗完成的有效Document列表
    """
    # 遍历所有文档 → 清洗 → 只保留清洗后有内容的文档
    return [clean_document(document) for document in documents if clean_text(document.page_content)]