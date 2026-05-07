from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ConfidenceLevel(Enum):
    VERY_LOW = 0.2
    LOW = 0.4
    MEDIUM = 0.6
    HIGH = 0.8
    VERY_HIGH = 0.95


@dataclass
class DiagnosisEntry:
    diagnosis: str
    confidence: float
    clinical_evidence: str

    def __lt__(self, other):
        return self.confidence < other.confidence


@dataclass
class WeightFeedback:
    my_weight_delta: float = 0.0
    peer_weight_suggestions: Dict[str, float] = field(default_factory=dict)
    adjustment_reason: str = ""


@dataclass
class DepartmentAgentResponse:
    department: str
    analysis_time: float
    primary_diagnosis: DiagnosisEntry
    differential_diagnoses: List[DiagnosisEntry] = field(default_factory=list)
    recommended_tests: List[str] = field(default_factory=list)
    referral_suggestions: List[Dict] = field(default_factory=list)
    knowledge_summary: str = ""
    knowledge_sources: List[str] = field(default_factory=list)
    task_assignment: Dict = field(default_factory=dict)
    handoff_to_main: Dict = field(default_factory=dict)
    weight_feedback: WeightFeedback = field(default_factory=WeightFeedback)
    clinical_interpretation: str = ""
    conflicts_with: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def get_confidence_level(self) -> str:
        conf = self.primary_diagnosis.confidence
        if conf >= 0.95:
            return "非常高"
        if conf >= 0.8:
            return "高"
        if conf >= 0.6:
            return "中等"
        if conf >= 0.4:
            return "低"
        return "非常低"

    def to_dict(self) -> dict:
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


__all__ = [
    "ConfidenceLevel",
    "DepartmentAgentResponse",
    "DiagnosisEntry",
    "WeightFeedback",
]

