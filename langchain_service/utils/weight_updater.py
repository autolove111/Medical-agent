"""
权重更新引擎

负责根据部门Agent的反馈动态调整GAT图的权重。
这是实现"自适应多轮对话"的关键组件。
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class WeightUpdateRecord:
    """权重更新记录"""
    timestamp: datetime
    department: str
    old_weight: float
    new_weight: float
    delta: float
    reason: str
    source: str  # "agent_feedback" 或 "consensus_feedback"


class WeightUpdater:
    """权重更新管理器"""
    
    def __init__(self, initial_weights: Optional[Dict[str, float]] = None):
        """
        Args:
            initial_weights: 初始权重，如 {"肾内科": 0.7, "血液科": 0.6, ...}
        """
        # 默认权重
        self.weights = initial_weights or {
            "肾内科": 0.6,
            "血液科": 0.6,
            "肝胆科": 0.5,
            "内分泌科": 0.5,
            "心内科": 0.6,
            "呼吸科": 0.5,
            "消化科": 0.5,
        }
        
        # 权重范围
        self.min_weight = 0.1
        self.max_weight = 2.0
        
        # 更新历史
        self.update_history: List[WeightUpdateRecord] = []
        
        # 累积反馈（用于批量更新）
        self.pending_feedback: List[Dict] = []
        
        # 学习率相关
        self.learning_rate = 0.1  # 基础学习率
        self.momentum = 0.9  # 动量系数
    
    def update_from_agent_feedback(
        self,
        department: str,
        weight_delta: float,
        reason: str,
        timestamp: Optional[datetime] = None
    ) -> float:
        """
        根据单个Agent的反馈直接更新权重
        
        Args:
            department: 科室名
            weight_delta: 权重变化量 (-0.3 ~ 0.3)
            reason: 调整原因
            timestamp: 时间戳
        
        Returns:
            新的权重值
        """
        timestamp = timestamp or datetime.now()
        old_weight = self.weights.get(department, 0.6)
        
        # 应用学习率
        actual_delta = weight_delta * self.learning_rate
        
        # 更新权重
        new_weight = old_weight + actual_delta
        new_weight = max(self.min_weight, min(self.max_weight, new_weight))
        
        # 记录
        self.weights[department] = new_weight
        self.update_history.append(WeightUpdateRecord(
            timestamp=timestamp,
            department=department,
            old_weight=old_weight,
            new_weight=new_weight,
            delta=actual_delta,
            reason=reason,
            source="agent_feedback"
        ))
        
        logger.info(
            f"【权重更新】{department}: {old_weight:.3f} → {new_weight:.3f} "
            f"(delta={actual_delta:+.3f}) | {reason}"
        )
        
        return new_weight
    
    def update_from_consensus(
        self,
        consensus_result: Dict,  # {"department": ..., "conflict_level": "low|medium|high", ...}
        primary_agent: str
    ) -> Dict[str, float]:
        """
        根据主Agent的共识决策更新权重
        
        规则：
        1. 置信度高且无冲突 → 权重↑
        2. 置信度低或有冲突 → 权重↓
        3. 冲突严重 → 权重↓↓
        
        Returns:
            更新后的所有权重字典
        """
        updates = {}
        
        for dept, result in consensus_result.items():
            old_weight = self.weights.get(dept, 0.6)
            
            # 基于共识的反馈
            conflict_level = result.get("conflict_level", "low")
            confidence = result.get("consensus_confidence", 0.5)
            
            # 计算权重调整
            if conflict_level == "high":
                delta = -0.15
                reason = "诊断冲突（严重）"
            elif conflict_level == "medium":
                delta = -0.08
                reason = "诊断冲突（中等）"
            else:
                # 无冲突，根据置信度调整
                delta = (confidence - 0.5) * 0.2
                reason = f"共识反馈 (置信度 {confidence:.1%})"
            
            # 应用更新
            actual_delta = delta * self.learning_rate
            new_weight = old_weight + actual_delta
            new_weight = max(self.min_weight, min(self.max_weight, new_weight))
            
            self.weights[dept] = new_weight
            updates[dept] = new_weight
            
            # 记录
            self.update_history.append(WeightUpdateRecord(
                timestamp=datetime.now(),
                department=dept,
                old_weight=old_weight,
                new_weight=new_weight,
                delta=actual_delta,
                reason=reason,
                source="consensus_feedback"
            ))
            
            logger.info(
                f"【共识反馈权重更新】{dept}: {old_weight:.3f} → {new_weight:.3f} | {reason}"
            )
        
        return updates
    
    def batch_update(self, feedback_list: List[Dict]) -> Dict[str, float]:
        """
        批量更新多个科室的权重
        
        Args:
            feedback_list: 反馈列表
            [
                {
                    "department": "肾内科",
                    "weight_delta": 0.1,
                    "reason": "诊断准确"
                },
                ...
            ]
        
        Returns:
            所有更新后的权重
        """
        logger.info(f"【批量权重更新】处理 {len(feedback_list)} 条反馈")
        
        for feedback in feedback_list:
            self.update_from_agent_feedback(
                department=feedback["department"],
                weight_delta=feedback.get("weight_delta", 0),
                reason=feedback.get("reason", "")
            )
        
        return self.weights.copy()
    
    def get_weights(self) -> Dict[str, float]:
        """获取当前权重"""
        return self.weights.copy()
    
    def get_weight(self, department: str) -> float:
        """获取单个科室的权重"""
        return self.weights.get(department, 0.6)
    
    def reset_weights(self, new_weights: Optional[Dict[str, float]] = None):
        """重置权重（用于新的诊断周期）"""
        if new_weights:
            self.weights = new_weights
            logger.info(f"【权重重置】使用新的权重点")
        else:
            # 恢复到初始值
            self.weights = {k: 0.6 for k in self.weights.keys()}
            logger.info(f"【权重重置】恢复到默认值 0.6")
    
    def get_update_history(self, department: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """
        获取权重更新历史
        
        Args:
            department: 特定科室，None 表示所有
            limit: 限制条数
        
        Returns:
            更新记录列表
        """
        records = self.update_history
        
        if department:
            records = [r for r in records if r.department == department]
        
        # 返回最新的 limit 条
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "department": r.department,
                "old_weight": r.old_weight,
                "new_weight": r.new_weight,
                "delta": r.delta,
                "reason": r.reason,
                "source": r.source,
            }
            for r in sorted(records, key=lambda x: x.timestamp, reverse=True)[:limit]
        ]
    
    def get_weight_statistics(self) -> Dict:
        """获取权重统计信息"""
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
        """
        导出权重供GAT模型使用
        
        将权重从 [0.1, 2.0] 范围归一化到 [0, 1]
        """
        normalized = {}
        weight_range = self.max_weight - self.min_weight
        
        for dept, weight in self.weights.items():
            # 线性归一化
            normalized[dept] = (weight - self.min_weight) / weight_range
        
        return normalized
    
    def decay_old_feedback(self, decay_hours: int = 24) -> None:
        """
        随时间衰退旧的反馈影响
        
        这是一个可选的功能，用于防止权重被长期锁定在某个值
        """
        cutoff_time = datetime.now() - timedelta(hours=decay_hours)
        
        # 计算衰退系数
        for record in self.update_history:
            if record.timestamp < cutoff_time:
                # 衰退该更新的影响（部分回滚）
                age_hours = (datetime.now() - record.timestamp).total_seconds() / 3600
                decay_factor = 0.95 ** (age_hours / decay_hours)  # 指数衰退
                
                # 逆向应用部分衰退
                partial_reversal = record.delta * (1 - decay_factor)
                
                dept = record.department
                current_weight = self.weights[dept]
                decayed_weight = current_weight - partial_reversal
                
                self.weights[dept] = max(
                    self.min_weight,
                    min(self.max_weight, decayed_weight)
                )
        
        logger.debug(f"【权重衰退】完成旧反馈衰退处理")


# 全局权重更新器实例
_global_weight_updater: Optional[WeightUpdater] = None


def get_weight_updater() -> WeightUpdater:
    """获取全局权重更新器"""
    global _global_weight_updater
    if _global_weight_updater is None:
        _global_weight_updater = WeightUpdater()
    return _global_weight_updater


def set_weight_updater(updater: WeightUpdater):
    """设置全局权重更新器"""
    global _global_weight_updater
    _global_weight_updater = updater
