
"""
短期记忆 — 会话期间的完整对话记录

所有消息存 PostgreSQL，不压缩，全量保留。
不区分会话，按用户线性存储。
"""

from __future__ import annotations

from harness.memory.persistence.repositories.events_record_repo import EventsRecordRepo


class EventsRecordMemory:

    def __init__(self, patient_id: str, repo: EventsRecordRepo):
        self.patient_id = patient_id
        self._repo = repo
        self._turn_id = 0

    @property
    def turn_id(self) -> int:
        return self._turn_id

    def append(self, role: str, content: str, metrics_involved: list[str] = None) -> int:
        """追加一条消息，返回当前轮次"""
        if role == "user":
            self._turn_id += 1
        
        self._repo.save_message(
            patient_id=self.patient_id,
            role=role,
            content=content,
            metrics_involved=metrics_involved,
        )
        return self._turn_id

    def get_time_history(self,  start_time: str = None, end_time: str = None) -> list[dict]:
        """获取历史消息，按时间倒序返回"""
        return self._repo.get_metrics_history(
            patient_id=self.patient_id,
            start_time=start_time,
            end_time=end_time,
        )
    
    def get_metrics_history(self, metrics: list[str]) -> list[dict]:
        """根据涉及的指标获取消息，按时间倒序返回"""
        return self._repo.search_by_metric(
            patient_id=self.patient_id,
            metrics=metrics,
        )

    @property
    def current_turn(self) -> int:
        return self._turn_id