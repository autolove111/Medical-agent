"""
部门Agent标准化响应格式

每个科室Agent返回一个统一的响应对象，包含：
1. 诊断结果
2. 医学证据
3. 对图权重的反馈
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class ConfidenceLevel(Enum):
    """诊断置信度级别"""
    VERY_LOW = 0.2
    LOW = 0.4
    MEDIUM = 0.6
    HIGH = 0.8
    VERY_HIGH = 0.95


@dataclass
class DiagnosisEntry:
    """诊断项"""
    diagnosis: str  # 诊断名称
    confidence: float  # 置信度 [0, 1]
    clinical_evidence: str  # 临床证据
    
    def __lt__(self, other):
        """支持按置信度排序"""
        return self.confidence < other.confidence


@dataclass
class WeightFeedback:
    """权重调整反馈"""
    # 自身权重调整
    my_weight_delta: float = 0.0  # -1.0 ~ +1.0，表示上升或下降
    
    # 对其他科室的权重建议
    peer_weight_suggestions: Dict[str, float] = field(default_factory=dict)
    # 例: {"血液科": -0.1, "心内科": +0.05}
    
    # 权重调整的理由
    adjustment_reason: str = ""


@dataclass
class DepartmentAgentResponse:
    """部门Agent的标准响应"""
    
    # 基础信息
    department: str  # 科室名称
    analysis_time: float  # 分析耗时（秒）
    
    # 诊断结果
    primary_diagnosis: DiagnosisEntry  # 主要诊断
    differential_diagnoses: List[DiagnosisEntry] = field(default_factory=list)  # 鉴别诊断
    
    # 建议
    recommended_tests: List[str] = field(default_factory=list)  # 建议进一步检查
    referral_suggestions: List[Dict] = field(default_factory=list)  # 转诊建议
    
    # 医学知识支持
    knowledge_summary: str = ""  # 检索出的相关医学知识摘要
    knowledge_sources: List[str] = field(default_factory=list)  # 知识来源

    # 主Agent下发的任务与科室回传主Agent的摘要
    task_assignment: Dict = field(default_factory=dict)
    handoff_to_main: Dict = field(default_factory=dict)
    
    # 权重反馈（关键）
    weight_feedback: WeightFeedback = field(default_factory=WeightFeedback)
    
    # 临床解读
    clinical_interpretation: str = ""
    
    # 与其他科室的冲突标记（如果有）
    conflicts_with: List[Dict] = field(default_factory=list)
    # [{"department": "血液科", "conflicting_point": "...", "severity": "low|medium|high"}]
    
    # 错误/警告
    warnings: List[str] = field(default_factory=list)
    
    def get_confidence_level(self) -> str:
        """获取诊断置信度级别描述"""
        conf = self.primary_diagnosis.confidence
        if conf >= 0.95:
            return "非常高"
        elif conf >= 0.8:
            return "高"
        elif conf >= 0.6:
            return "中等"
        elif conf >= 0.4:
            return "低"
        else:
            return "非常低"
    
    def to_dict(self) -> dict:
        """转换为字典（用于序列化）"""
        return {
            "department": self.department,
            "analysis_time": self.analysis_time,
            "primary_diagnosis": {
                "diagnosis": self.primary_diagnosis.diagnosis,
                "confidence": self.primary_diagnosis.confidence,
                "confidence_level": self.get_confidence_level(),
                "clinical_evidence": self.primary_diagnosis.clinical_evidence,
            },
            "differential_diagnoses": [
                {
                    "diagnosis": d.diagnosis,
                    "confidence": d.confidence,
                    "clinical_evidence": d.clinical_evidence,
                }
                for d in sorted(self.differential_diagnoses, reverse=True)
            ],
            "recommended_tests": self.recommended_tests,
            "referral_suggestions": self.referral_suggestions,
            "knowledge_summary": self.knowledge_summary,
            "knowledge_sources": self.knowledge_sources,
            "task_assignment": self.task_assignment,
            "handoff_to_main": self.handoff_to_main,
            "weight_feedback": {
                "my_weight_delta": self.weight_feedback.my_weight_delta,
                "peer_weight_suggestions": self.weight_feedback.peer_weight_suggestions,
                "adjustment_reason": self.weight_feedback.adjustment_reason,
            },
            "clinical_interpretation": self.clinical_interpretation,
            "conflicts_with": self.conflicts_with,
            "warnings": self.warnings,
        }
    
    def __str__(self) -> str:
        """友好的字符串表示"""
        output = f"""
【{self.department}诊断结果】
┌─ 主诊断：{self.primary_diagnosis.diagnosis} (置信度: {self.primary_diagnosis.confidence:.1%} - {self.get_confidence_level()})
│  证据：{self.primary_diagnosis.clinical_evidence}
├─ 鉴别诊断：
"""
        for diag in sorted(self.differential_diagnoses, reverse=True)[:3]:
            output += f"│  · {diag.diagnosis} ({diag.confidence:.1%})\n"
        
        output += f"""├─ 建议检查：{', '.join(self.recommended_tests) if self.recommended_tests else '无'}
├─ 权重调整：{self.weight_feedback.my_weight_delta:+.2f}
└─ 分析耗时：{self.analysis_time:.2f}s
"""
        return output
