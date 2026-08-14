"""
短期记忆存储 — Redis 后端

存储 OpenAI 标准消息格式：
  {"role": "user",      "content": "..."}
  {"role": "assistant", "content": "..."}
  {"role": "assistant", "tool_calls": [...]}
  {"role": "tool",      "tool_call_id": "...", "content": "..."}

数据存在 Redis Hash 里，按 user_id + session_id 隔离。
任何 Worker 进程都能访问同一份记忆。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import redis

from core.config import settings

logger = logging.getLogger(__name__)


_redis_client: redis.Redis = None


def _get_redis() -> redis.Redis:
    """获取 Redis 连接（全局单例）。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
        )
    return _redis_client


class ShortMemoryStore:
    """短期记忆（Redis 后端）。

    所有数据存在 Redis Hash: medlab:stm:{user_id}:{session_id}
    API 和原来完全一样，外部代码无感知。
    """

    # TTL: 2 小时（7200 秒）
    _ttl = 7200

    def __init__(self, user_id: str = "", session_id: str = ""):
        self.user_id = user_id
        self.session_id = session_id
        self._redis_key = f"medlab:stm:{user_id}:{session_id}"
        self._sync_key = f"medlab:stm:{user_id}:{session_id}:sync"

        # 缓存 window_control 实例
        from loop.context_window.window_control import ContextWindowControl
        self.window_control = ContextWindowControl()

    # ── Redis 读写 ──

    def _load(self) -> dict:
        """从 Redis 加载全部数据。"""
        r = _get_redis()
        data = r.hgetall(self._redis_key)
        if not data:
            return {
                "messages": "[]", "summary": "[]", "message_len": "0",
            }
        return data

    def _save_messages(self, messages: list, summary: list, message_len: int):
        """保存记忆数据到 Redis。"""
        r = _get_redis()
        r.hset(self._redis_key, "messages", json.dumps(messages, ensure_ascii=False))
        r.hset(self._redis_key, "summary", json.dumps(summary, ensure_ascii=False))
        r.hset(self._redis_key, "message_len", str(message_len))
        r.expire(self._redis_key, self._ttl)  # 设置 TTL 2小时

    # ── 同步队列（Write-Behind 用） ──

    def _push_sync(self, role: str, content: str):
        """追加一条消息到待同步队列（不被压缩影响）。"""
        r = _get_redis()
        r.rpush(self._sync_key, json.dumps({
            "role": role,
            "content": content,
        }, ensure_ascii=False))

    def pop_sync_batch(self, batch_size: int = 100) -> list[dict]:
        """从同步队列批量取出并删除，返回消息列表。"""
        r = _get_redis()
        pipe = r.pipeline()
        pipe.lrange(self._sync_key, 0, batch_size - 1)
        pipe.ltrim(self._sync_key, batch_size, -1)
        results = pipe.execute()
        items = results[0]
        return [json.loads(x) for x in items]

    def sync_pending_count(self) -> int:
        """同步队列中待写入的条数。"""
        r = _get_redis()
        return r.llen(self._sync_key)

    def clear_messages(self) -> None:
        """清空消息列表（新任务开始时调用，避免跨任务消息混杂）。"""
        r = _get_redis()
        r.hset(self._redis_key, "messages", "[]")
        r.hset(self._redis_key, "message_len", "0")
        r.expire(self._redis_key, self._ttl)

    @property
    def messages(self) -> list[dict]:
        """获取消息列表，并验证消息格式完整性。"""
        data = self._load()
        messages = json.loads(data.get("messages", "[]"))
        return self._validate_messages(messages)

    @staticmethod
    def _validate_messages(messages: list[dict]) -> list[dict]:
        """验证消息格式：确保每个 tool 消息前面都有带 tool_calls 的 assistant 消息。"""
        if not messages:
            return messages

        validated = []
        has_pending_tool_calls = False  # 前面是否有 assistant 消息带 tool_calls

        for msg in messages:
            role = msg.get("role")

            if role == "assistant":
                has_pending_tool_calls = bool(msg.get("tool_calls"))
                validated.append(msg)
            elif role == "tool":
                if has_pending_tool_calls:
                    validated.append(msg)
                    has_pending_tool_calls = False  # 消费掉
                # else: 跳过孤立的 tool 消息
            else:
                has_pending_tool_calls = False
                validated.append(msg)

        return validated

    @messages.setter
    def messages(self, value: list[dict]):
        """设置消息列表。"""
        data = self._load()
        summary = json.loads(data.get("summary", "[]"))
        message_len = int(data.get("message_len", "0"))
        # 重新计算长度
        message_len = sum(len(m.get("content", "") or "") for m in value)
        self._save_messages(value, summary, message_len)

    @property
    def summary(self) -> list[dict]:
        """获取摘要列表。"""
        data = self._load()
        return json.loads(data.get("summary", "[]"))

    @summary.setter
    def summary(self, value: list[dict]):
        """设置摘要列表。"""
        data = self._load()
        messages = json.loads(data.get("messages", "[]"))
        message_len = int(data.get("message_len", "0"))
        self._save_messages(messages, value, message_len)

    @property
    def message_len(self) -> int:
        """获取消息总长度。"""
        data = self._load()
        return int(data.get("message_len", "0"))

    @message_len.setter
    def message_len(self, value: int):
        """设置消息总长度。"""
        r = _get_redis()
        r.hset(self._redis_key, "message_len", str(value))

    # ── 写入操作 ──

    def add_user_message(self, content: str) -> None:
        """添加用户消息，超限时自动压缩。"""
        messages = self.messages
        messages.append({"role": "user", "content": content})
        new_len = self.message_len + len(content)
        self._save_messages(messages, self.summary, new_len)
        self._push_sync("user", content)
        logger.info("STM add_user_message | key=%s msg_count=%d content=%s",
                    self._redis_key, len(messages), content[:80])

        # 检查是否需要压缩
        if new_len > self.window_control.get_limit("history").chars:
            self.compress_messages(
                summary_len=self.window_control.get_limit("summary").chars
            )

    def add_assistant_message(self, content: str, reasoning_content: str = None) -> None:
        """添加助手文本回复。"""
        messages = self.messages
        msg = {"role": "assistant", "content": content}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        messages.append(msg)
        new_len = self.message_len + len(content) + (len(reasoning_content) if reasoning_content else 0)
        self._save_messages(messages, self.summary, new_len)
        self._push_sync("assistant", content)

    def add_assistant_tool_calls(self, content: str, tool_calls: list[dict], reasoning_content: str = None) -> None:
        """添加助手的工具调用请求。按 DeepSeek 标准，有 tool_calls 时 content 为 null。"""
        total_len = len(content) if content else 0
        for tc in tool_calls:
            fn = tc.get("function", {})
            total_len += len(fn.get("name", ""))
            total_len += len(fn.get("arguments", ""))
        if reasoning_content:
            total_len += len(reasoning_content)

        messages = self.messages
        msg = {"role": "assistant", "content": None, "tool_calls": tool_calls}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        messages.append(msg)

        new_len = self.message_len + total_len
        self._save_messages(messages, self.summary, new_len)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """添加工具执行结果。"""
        messages = self.messages
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })
        new_len = self.message_len + len(content) + len(tool_call_id)
        self._save_messages(messages, self.summary, new_len)

    # ── 压缩 ──

    def compress_messages(self, summary_len: int) -> None:
        """压缩早期消息为摘要，释放上下文空间。"""
        from llm.chat_model import ChatModel
        llm = ChatModel()

        messages = self.messages
        if len(messages) < 4:
            return

        mid = len(messages) // 2

        # 找到安全的切分点：确保不切断 assistant+tool 消息对
        # 向后找，直到切分点不在 tool 消息中间
        while mid < len(messages) and messages[mid].get("role") == "tool":
            mid += 1
        # 如果 mid 超出范围，向前找
        if mid >= len(messages):
            mid = len(messages) // 2
            while mid > 0 and messages[mid].get("role") == "tool":
                mid -= 1

        old_messages = messages[:mid]

        content_parts = []

        current_summary = self.summary
        if current_summary:
            content_parts.append(f"【已有摘要】\n{current_summary[0]['content']}")

        conversation_lines = []
        for i, m in enumerate(old_messages):
            role = m.get('role', '?')
            content = m.get('content', '') or ''
            conversation_lines.append(f"[{i}][{role}] {content}")
        content_parts.append("【待压缩对话】\n" + "\n".join(conversation_lines))

        combined_content = "\n\n".join(content_parts)

        compress_prompt = [
            {"role": "system", "content": (
                "将以下医疗问诊对话压缩为要点摘要，遵循规则：\n"
                "1. 保留：症状、用药、过敏史、诊断结论、数字参数、用户明确偏好\n"
                "2. 删除：礼貌用语、重复确认、过程描述、非结论性思考\n"
                "3. 合并：将分散的相关信息合并为一条\n"
                "4. 保持时序：按原顺序提炼\n"
                f"5. 字数不能超过{summary_len}个字符\n"
                "直接输出摘要内容，不要有其他说明。"
            )},
            {"role": "user", "content": combined_content}
        ]

        response = llm.invoke(compress_prompt)
        summary_text = response.choices[0].message.content.strip()

        # 更新
        new_summary = [{"role": "system", "content": f"会话摘要（基于历史消息压缩生成）:\n{summary_text}"}]
        remaining = messages[mid:]
        new_len = sum(len(m.get("content", "") or "") for m in remaining)

        self._save_messages(remaining, new_summary, new_len)
