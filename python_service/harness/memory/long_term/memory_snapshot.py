"""
记忆快照 — 存取 messages / summary / message_len
"""

from __future__ import annotations
from typing import Optional

from harness.memory.persistence.repositories.memory_snapshot_repo import MemorySnapshotRepo


class MemorySnapshotMemory:

    def __init__(self, repo: MemorySnapshotRepo):
        self._repo = repo

    def save(self, patient_id: str, session_id: str,
             messages: list[dict], summary: list[dict], message_len: int) -> None:
        """存入快照"""
        self._repo.save(patient_id, session_id, messages, summary, message_len)

    def load(self, patient_id: str, session_id: str) -> Optional[dict]:
        """读取快照，返回 {messages, summary, message_len} 或 None"""
        return self._repo.load(patient_id, session_id)
