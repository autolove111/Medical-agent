"""
MemorySystem — 记忆系统唯一对外入口

三层记忆：
  ShortMemoryStore    — 短期记忆（Redis 后端，FC 格式）
  EventsRecordMemory  — 对话记录（只读层，从 PG 查询）
  ProfileMemory       — 患者画像（跨会话永久存储）

写入策略：
  - 短期记忆：立即写 Redis，同时追加到 Redis 同步队列
  - 对话记录：Write-Behind（后台线程从 Redis 同步队列批量刷入 PG）
  - 患者画像：Write-Through（同步写入 PG）
"""

from __future__ import annotations
import logging

from memory.long_term.events_record import EventsRecordMemory
from memory.long_term.profile import ProfileMemory
from memory.long_term.memory_snapshot import MemorySnapshotMemory
from memory.long_term.event_buffer import EventBuffer
from memory.short_memory.store import ShortMemoryStore
from memory.persistence.repositories.profile_repo import ProfileRepo
from memory.persistence.repositories.events_record_repo import EventsRecordRepo
from memory.persistence.repositories.memory_snapshot_repo import MemorySnapshotRepo


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
        # Long-term memory（读取层）
        self.profile = ProfileMemory(self._profile_repo, userid)
        self.events = EventsRecordMemory(userid, self._events_repo)
        self.snapshot = MemorySnapshotMemory(self._snapshot_repo)
        # Short memory（Redis 后端）
        self._stm = ShortMemoryStore(user_id=userid, session_id=session_id)
        # Write-Behind 缓冲（从 Redis 同步队列读 → 写 PG）
        self._buffer = EventBuffer(user_id=userid, session_id=session_id)
        self._buffer.start()

    # ========== 写入（Write-Behind）==========

    def on_user_message(self, content: str, scores: dict = None) -> None:
        """用户消息：写 Redis + 同步队列，后台线程异步写 PG。"""
        self._stm.add_user_message(content)
        logger.debug("on_user_message: stm_count=%d", len(self._stm.messages))

    def on_assistant_message(self, content: str, scores: dict = None, reasoning_content: str = None) -> None:
        """助手回复：写 Redis + 同步队列，后台线程异步写 PG。"""
        self._stm.add_assistant_message(content, reasoning_content=reasoning_content)

    def on_assistant_tool_calls(self, content: str, tool_calls: list[dict], reasoning_content: str = None) -> None:
        """工具调用：只写 Redis（中间过程不写 PG）。"""
        self._stm.add_assistant_tool_calls(content, tool_calls, reasoning_content=reasoning_content)

    def on_tool_result(self, tool_call_id: str, content: str) -> None:
        """工具结果：只写 Redis（中间过程不写 PG）。"""
        self._stm.add_tool_result(tool_call_id, content)

    def flush_sync(self):
        """同步刷盘：确保 Redis 同步队列中的所有消息写入 PG。"""
        self._buffer.flush_sync()

    def update_profile(self, updates: dict) -> None:
        """更新患者画像（直接写 PG，不走缓冲）。"""
        self.profile.update(updates)

    # ========== 读取 ==========

    def get_short_memory_text(self) -> list[dict]:
        """获取短期记忆消息列表（FC 格式）。"""
        if self._stm:
            return self._stm.messages
        return []

    def get_summary_text(self) -> list[dict]:
        """获取短期记忆摘要列表。"""
        if self._stm:
            return self._stm.summary
        return []

    def get_profile_text(self) -> dict:
        """获取患者画像。"""
        profile = self.profile.get()
        if not profile:
            return {}
        return profile

    # ========== 快照 ==========

    def save_snapshot(self) -> None:
        """将当前短期记忆存入快照。"""
        if self._stm:
            logger.debug("save_snapshot: stm_count=%d", len(self._stm.messages))
            self.snapshot.save(
                patient_id=self.patient_id,
                session_id=self.session_id,
                messages=self._stm.messages,
                summary=self._stm.summary,
                message_len=self._stm.message_len,
            )

    def load_snapshot(self) -> bool:
        """从快照恢复短期记忆，返回是否成功。"""
        data = self.snapshot.load(self.patient_id, self.session_id)
        if data:
            self._stm.messages = data["messages"]
            self._stm.summary = data["summary"]
            self._stm.message_len = data["message_len"]
            logger.debug("load_snapshot: loaded %d messages", len(self._stm.messages))
            return True
        logger.debug("load_snapshot: no snapshot found")
        return False

    # ========== 结束 ==========

    def end_session(self) -> None:
        """结束会话：同步刷盘 + 保存快照。"""
        self.flush_sync()
        self.save_snapshot()


__all__ = ["MemorySystem"]
