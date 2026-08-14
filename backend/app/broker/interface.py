"""
消息队列接口定义

所有 Worker 只依赖这个接口，不关心底层是 Redis、Kafka 还是内存。
启动时注入具体实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class MessageBroker(ABC):
    """消息队列抽象接口"""

    # ── 主任务（FastAPI → Loop Worker）──

    @abstractmethod
    def submit_task(self, user_id: str, session_id: str, query: str, task_type: str = "chat") -> str:
        """提交任务，返回 task_id。"""
        ...

    @abstractmethod
    def pop_task(self, timeout: int = 0) -> Optional[dict]:
        """从主队列拉取任务。"""
        ...

    @abstractmethod
    def update_task_status(self, task_id: str, status: str, task_type: str = "chat", **extra) -> None:
        """更新主任务状态。task_type: 'chat' | 'ocr'"""
        ...

    @abstractmethod
    def get_task_status(self, task_id: str, task_type: str = "chat") -> Optional[dict]:
        """查询主任务状态。task_type: 'chat' | 'ocr'"""
        ...

    # ── LLM 请求队列（Loop Worker → LLM Worker）──

    @abstractmethod
    def submit_llm_request(self, task_id: str, messages: list, tools: list = None) -> None:
        """提交 LLM 请求。"""
        ...

    @abstractmethod
    def pop_llm_request(self, timeout: int = 0) -> Optional[dict]:
        """LLM Worker 拉取请求。"""
        ...

    # ── LLM 结果队列（LLM Worker → Loop Worker）──

    @abstractmethod
    def push_llm_result(self, message: dict) -> None:
        """LLM Worker 推送结果。"""
        ...

    @abstractmethod
    def pop_llm_result(self, timeout: int = 0) -> Optional[dict]:
        """Loop Worker 拉取 LLM 结果。"""
        ...

    # ── RAG 请求队列（Loop Worker → RAG Worker）──

    @abstractmethod
    def submit_rag_request(self, task_id: str, query: str, top_k: int = 5) -> None:
        """提交 RAG 请求。"""
        ...

    @abstractmethod
    def pop_rag_request(self, timeout: int = 0) -> Optional[dict]:
        """RAG Worker 拉取请求。"""
        ...

    # ── RAG 结果队列（RAG Worker → Loop Worker）──

    @abstractmethod
    def push_rag_result(self, message: dict) -> None:
        """RAG Worker 推送结果。"""
        ...

    @abstractmethod
    def pop_rag_result(self, timeout: int = 0) -> Optional[dict]:
        """Loop Worker 拉取 RAG 结果。"""
        ...

    # ── OCR 请求队列（API → OCR Worker）──

    @abstractmethod
    def submit_ocr_request(self, task_id: str, file_path: str, file_type: str = "image") -> None:
        """提交 OCR 请求。file_type: 'image' | 'pdf'"""
        ...

    @abstractmethod
    def pop_ocr_request(self, timeout: int = 0) -> Optional[dict]:
        """OCR Worker 拉取请求。"""
        ...

    # ── 多队列阻塞读取 ──

    @abstractmethod
    def pop_any(self, timeout: int = 5) -> tuple[str, Optional[dict]]:
        """同时阻塞读取 task/llm_result/rag_result，返回 (来源, 数据)。"""
        ...

    # ── Pub/Sub（实时推送）──

    @abstractmethod
    def publish_stream_chunk(self, task_id: str, chunk_type: str, data: dict) -> None:
        """发布流式输出片段。"""
        ...
