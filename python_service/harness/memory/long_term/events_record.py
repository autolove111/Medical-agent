
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

    def append(self, role: str, content: str, scores: dict = None, metrics_involved: list[str] = None) -> int:
        """追加一条消息，可选写入评分，返回当前轮次"""
        if role == "user":
            self._turn_id += 1

        self._repo.save_message(
            patient_id=self.patient_id,
            role=role,
            content=content,
            scores=scores,
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

    def update_scores(self, scores: list[dict]) -> None:
        """将多维评分回写到最近的消息记录。

        Args:
            scores: [{"medical": 0.9, "experience": 0.2, "profile": 0.1}, ...]
        """
        if not scores:
            return
        for score_item in scores:
            self._repo.update_message_scores(
                patient_id=self.patient_id,
                scores={
                    "medical": score_item.get("medical", 0.0),
                    "experience": score_item.get("experience", 0.0),
                    "profile": score_item.get("profile", 0.0),
                },
            )

    @property
    def current_turn(self) -> int:
        return self._turn_id