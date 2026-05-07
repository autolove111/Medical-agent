"""
权重更新引擎

负责根据部门 Agent 的反馈动态调整图的权重。
这是实现“自适应多轮对话”的关键组件。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WeightUpdateRecord:
    timestamp: datetime
    department: str
    old_weight: float
    new_weight: float
    delta: float
    reason: str
    source: str


class WeightUpdater:
    def __init__(self, initial_weights: Optional[Dict[str, float]] = None):
        self.weights = initial_weights or {
            "肾内科": 0.6,
            "血液科": 0.6,
            "肝胆科": 0.5,
            "内分泌科": 0.5,
            "心内科": 0.6,
            "呼吸科": 0.5,
            "消化科": 0.5,
        }
        self.min_weight = 0.1
        self.max_weight = 2.0
        self.update_history: List[WeightUpdateRecord] = []
        self.pending_feedback: List[Dict] = []
        self.learning_rate = 0.1
        self.momentum = 0.9

    def update_from_agent_feedback(
        self,
        department: str,
        weight_delta: float,
        reason: str,
        timestamp: Optional[datetime] = None,
    ) -> float:
        timestamp = timestamp or datetime.now()
        old_weight = self.weights.get(department, 0.6)
        actual_delta = weight_delta * self.learning_rate
        new_weight = old_weight + actual_delta
        new_weight = max(self.min_weight, min(self.max_weight, new_weight))

        self.weights[department] = new_weight
        self.update_history.append(
            WeightUpdateRecord(
                timestamp=timestamp,
                department=department,
                old_weight=old_weight,
                new_weight=new_weight,
                delta=actual_delta,
                reason=reason,
                source="agent_feedback",
            )
        )

        logger.info(
            "【权重更新】%s: %.3f -> %.3f (delta=%+.3f) | %s",
            department,
            old_weight,
            new_weight,
            actual_delta,
            reason,
        )
        return new_weight

    def update_from_consensus(
        self,
        consensus_result: Dict,
        primary_agent: str,
    ) -> Dict[str, float]:
        updates = {}

        for dept, result in consensus_result.items():
            old_weight = self.weights.get(dept, 0.6)
            conflict_level = result.get("conflict_level", "low")
            confidence = result.get("consensus_confidence", 0.5)

            if conflict_level == "high":
                delta = -0.15
                reason = "诊断冲突（严重）"
            elif conflict_level == "medium":
                delta = -0.08
                reason = "诊断冲突（中等）"
            else:
                delta = (confidence - 0.5) * 0.2
                reason = f"共识反馈 (置信度 {confidence:.1%})"

            actual_delta = delta * self.learning_rate
            new_weight = old_weight + actual_delta
            new_weight = max(self.min_weight, min(self.max_weight, new_weight))

            self.weights[dept] = new_weight
            updates[dept] = new_weight
            self.update_history.append(
                WeightUpdateRecord(
                    timestamp=datetime.now(),
                    department=dept,
                    old_weight=old_weight,
                    new_weight=new_weight,
                    delta=actual_delta,
                    reason=reason,
                    source="consensus_feedback",
                )
            )

            logger.info(
                "【共识反馈权重更新】%s: %.3f -> %.3f | %s",
                dept,
                old_weight,
                new_weight,
                reason,
            )

        return updates

    def batch_update(self, feedback_list: List[Dict]) -> Dict[str, float]:
        logger.info("【批量权重更新】处理 %d 条反馈", len(feedback_list))
        for feedback in feedback_list:
            self.update_from_agent_feedback(
                department=feedback["department"],
                weight_delta=feedback.get("weight_delta", 0),
                reason=feedback.get("reason", ""),
            )
        return self.weights.copy()

    def get_weights(self) -> Dict[str, float]:
        return self.weights.copy()

    def get_weight(self, department: str) -> float:
        return self.weights.get(department, 0.6)

    def reset_weights(self, new_weights: Optional[Dict[str, float]] = None):
        if new_weights:
            self.weights = new_weights
            logger.info("【权重重置】使用新的权重点")
        else:
            self.weights = {key: 0.6 for key in self.weights.keys()}
            logger.info("【权重重置】恢复到默认值 0.6")

    def get_update_history(self, department: Optional[str] = None, limit: int = 20) -> List[Dict]:
        records = self.update_history
        if department:
            records = [record for record in records if record.department == department]

        return [
            {
                "timestamp": record.timestamp.isoformat(),
                "department": record.department,
                "old_weight": record.old_weight,
                "new_weight": record.new_weight,
                "delta": record.delta,
                "reason": record.reason,
                "source": record.source,
            }
            for record in sorted(records, key=lambda item: item.timestamp, reverse=True)[:limit]
        ]

    def get_weight_statistics(self) -> Dict:
        if not self.weights:
            return {}

        values = list(self.weights.values())
        return {
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "total_departments": len(self.weights),
            "total_updates": len(self.update_history),
            "last_update": self.update_history[-1].timestamp.isoformat() if self.update_history else None,
        }

    def export_for_gat(self) -> Dict[str, float]:
        normalized = {}
        weight_range = self.max_weight - self.min_weight
        for dept, weight in self.weights.items():
            normalized[dept] = (weight - self.min_weight) / weight_range
        return normalized

    def decay_old_feedback(self, decay_hours: int = 24) -> None:
        cutoff_time = datetime.now() - timedelta(hours=decay_hours)
        for record in self.update_history:
            if record.timestamp < cutoff_time:
                age_hours = (datetime.now() - record.timestamp).total_seconds() / 3600
                decay_factor = 0.95 ** (age_hours / decay_hours)
                partial_reversal = record.delta * (1 - decay_factor)
                dept = record.department
                current_weight = self.weights[dept]
                decayed_weight = current_weight - partial_reversal
                self.weights[dept] = max(self.min_weight, min(self.max_weight, decayed_weight))

        logger.debug("【权重衰退】完成旧反馈衰退处理")


_global_weight_updater: Optional[WeightUpdater] = None


def get_weight_updater() -> WeightUpdater:
    global _global_weight_updater
    if _global_weight_updater is None:
        _global_weight_updater = WeightUpdater()
    return _global_weight_updater


def set_weight_updater(updater: WeightUpdater):
    global _global_weight_updater
    _global_weight_updater = updater


__all__ = [
    "WeightUpdateRecord",
    "WeightUpdater",
    "get_weight_updater",
    "set_weight_updater",
]
