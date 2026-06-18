"""
MemorySystem — 记忆系统唯一对外入口

三层记忆：
  ShortMemoryStore    — 短期记忆（FC 格式，直接传给 LLM）
  EventsRecordMemory  — 对话记录（全量持久化到 PG）
  ProfileMemory       — 患者画像（跨会话永久存储）

快照：
  MemorySnapshotMemory — 短期记忆快照（存取 messages/summary/message_len）
"""

from __future__ import annotations
import logging

from harness.memory.long_term.events_record import EventsRecordMemory
from harness.memory.long_term.profile import ProfileMemory
from harness.memory.long_term.memory_snapshot import MemorySnapshotMemory
from harness.memory.short_memory.store import ShortMemoryStore
from harness.memory.persistence.repositories.profile_repo import ProfileRepo
from harness.memory.persistence.repositories.events_record_repo import EventsRecordRepo
from harness.memory.persistence.repositories.memory_snapshot_repo import MemorySnapshotRepo


logger = logging.getLogger(__name__)


class MemorySystem:
    """记忆系统总入口，所有外部代码只和这个类交互"""

    def __init__(self, userid: str, session_id: str, db_session=None):
        # 用户 & 会话标识
        self.patient_id = userid
        self.session_id = session_id
        # Repos
        self._profile_repo = ProfileRepo(db_session)
        self._events_repo = EventsRecordRepo(db_session)
        self._snapshot_repo = MemorySnapshotRepo(db_session)
        # Long-term memory
        self.profile = ProfileMemory(self._profile_repo, userid)
        self.events = EventsRecordMemory(userid, self._events_repo)
        self.snapshot = MemorySnapshotMemory(self._snapshot_repo)
        # Short memory
        self._stm = ShortMemoryStore()

    # ========== 写入 ==========

    def on_user_message(self, content: str) -> None:
        """将用户消息写入对话记录和短期记忆"""
        self.events.append("user", content)
        self._stm.add_user_message(content)

    def on_assistant_message(self, content: str) -> None:
        """将助手回复写入对话记录和短期记忆"""
        self.events.append("assistant", content)
        self._stm.add_assistant_message(content)

    def on_assistant_tool_calls(self, content: str, tool_calls: list[dict]) -> None:
        """将助手的工具调用请求写入短期记忆"""
        self._stm.add_assistant_tool_calls(content, tool_calls)

    def on_tool_result(self, tool_call_id: str, content: str) -> None:
        """将工具执行结果写入短期记忆"""
        self._stm.add_tool_result(tool_call_id, content)

    # ========== 读取 ==========

    def get_short_memory_text(self) -> list[dict]:
        """获取短期记忆消息列表（FC 格式）"""
        if self._stm:
            return self._stm.messages
        return []

    def get_summary_text(self) -> list[dict]:
        """获取短期记忆摘要列表"""
        if self._stm:
            return self._stm.summary
        return []

    def get_profile_text(self) -> dict:
        """获取患者画像"""
        profile = self.profile.get()
        if not profile:
            return {}
        return profile

    # ========== 快照 ==========

    def save_snapshot(self) -> None:
        """将当前短期记忆存入快照"""
        if self._stm:
            self.snapshot.save(
                patient_id=self.patient_id,
                session_id=self.session_id,
                messages=self._stm.messages,
                summary=self._stm.summary,
                message_len=self._stm.message_len,
            )

    def load_snapshot(self) -> bool:
        """从快照恢复短期记忆，返回是否成功"""
        data = self.snapshot.load(self.patient_id, self.session_id)
        if data:
            self._stm.messages = data["messages"]
            self._stm.summary = data["summary"]
            self._stm.message_len = data["message_len"]
            return True
        return False

    # ========== 结束 ==========

    def end_session(self) -> None:
        """结束会话：保存快照 + 更新画像"""
        self.save_snapshot()
        self._stm = None


__all__ = ["MemorySystem"]
