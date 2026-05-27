"""
LabReport / LabIndicator 数据模型

结构化化验报告，贯穿整个报告处理管线：
- OCR 提取 → LabIndicator 列表
- 参考范围匹配 → 状态判定
- Agent 对话 → 报告上下文注入
"""

from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LabIndicator:
    """单个检验指标"""
    key: str                                    # 标准化键名，如 "creatinine"
    name: str                                   # 中文名称，如 "血肌酐"
    value: float                                # 数值
    unit: str = ""                              # 单位
    ref_range: str = ""                         # 参考范围文本，如 "60-115 μmol/L"
    status: str = "normal"                      # normal / high / low / critical_high / critical_low
    description: str = ""                       # 临床意义简述
    is_critical: bool = False                   # 是否危急值

    def to_context_text(self) -> str:
        """生成注入 prompt 的单项文本"""
        flag = {"high": "↑", "low": "↓", "critical_high": "↑↑ 危急", "critical_low": "↓↓ 危急"}.get(self.status, "")
        parts = [f"{self.name}（{self.key}）：{self.value} {self.unit}"]
        if self.ref_range:
            parts.append(f"参考范围：{self.ref_range}")
        if flag:
            parts.append(f"状态：{flag}")
        if self.description:
            parts.append(f"临床意义：{self.description}")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "value": self.value,
            "unit": self.unit, "ref_range": self.ref_range,
            "status": self.status, "description": self.description,
            "is_critical": self.is_critical,
        }


@dataclass
class LabReport:
    """一份完整的化验报告"""
    report_id: str                              # 唯一标识，如 rpt_abc123_202605261430
    user_id: str = "default"
    report_date: str = ""                       # 检验日期，YYYY-MM-DD
    file_path: str = ""                         # 原始文件路径
    indicators: list[LabIndicator] = field(default_factory=list)
    abnormal_indicators: list[LabIndicator] = field(default_factory=list)
    normal_indicators: list[LabIndicator] = field(default_factory=list)
    raw_ocr_text: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @property
    def total_count(self) -> int:
        return len(self.indicators)

    @property
    def abnormal_count(self) -> int:
        return len(self.abnormal_indicators)

    @property
    def normal_count(self) -> int:
        return len(self.normal_indicators)

    @property
    def has_critical(self) -> bool:
        return any(ind.is_critical for ind in self.indicators)

    def get_critical_indicators(self) -> list[LabIndicator]:
        return [ind for ind in self.indicators if ind.is_critical]

    def to_context_text(self) -> str:
        """生成注入 Agent prompt 的完整报告文本"""
        lines = [
            f"【化验报告 {self.report_id}】",
            f"检验日期：{self.report_date}",
            f"共检测 {self.total_count} 项指标",
        ]

        if self.abnormal_indicators:
            lines.append(f"\n⚠️ 异常指标（{self.abnormal_count} 项）：")
            for ind in self.abnormal_indicators:
                lines.append(f"  - {ind.to_context_text()}")

        if self.normal_indicators:
            lines.append(f"\n✅ 正常指标（{self.normal_count} 项）：")
            for ind in self.normal_indicators[:10]:  # 正常项最多显示 10 条
                lines.append(f"  - {ind.name}：{ind.value} {ind.unit}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "user_id": self.user_id,
            "report_date": self.report_date,
            "file_path": self.file_path,
            "total_count": self.total_count,
            "abnormal_count": self.abnormal_count,
            "normal_count": self.normal_count,
            "has_critical": self.has_critical,
            "indicators": [ind.to_dict() for ind in self.indicators],
            "created_at": self.created_at,
        }

    def save(self, directory: str) -> str:
        """保存报告为 JSON 文件"""
        path = f"{directory}/{self.report_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> Optional["LabReport"]:
        """从 JSON 文件加载报告"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            report = cls(
                report_id=data["report_id"],
                user_id=data.get("user_id", "default"),
                report_date=data.get("report_date", ""),
                file_path=data.get("file_path", ""),
                created_at=data.get("created_at", ""),
            )
            for ind_data in data.get("indicators", []):
                ind = LabIndicator(**ind_data)
                report.indicators.append(ind)
                if ind.status != "normal":
                    report.abnormal_indicators.append(ind)
                else:
                    report.normal_indicators.append(ind)
            return report
        except Exception:
            return None
