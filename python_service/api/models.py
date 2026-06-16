"""
API 请求/响应 Pydantic 模型
"""

from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(default="default", description="用户唯一标识")
    message: str = Field(..., min_length=1, max_length=5000, description="用户输入")
    report_id: Optional[str] = Field(default=None, description="关联的报告 ID（上报解读场景）")
    use_agent_loop: bool = Field(default=False, description="是否启用 AgentLoop 多步推理（Phase 5）")


class SourceItem(BaseModel):
    source: str = Field(default="", description="来源文档名")
    section: str = Field(default="", description="章节名")
    excerpt: str = Field(default="", description="原文片段")
    category: str = Field(default="", description="引用类别：indicator/correlation/diet/exercise/rag")
    indicators: List[str] = Field(default_factory=list, description="关联的指标 key")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="模型回复")
    sources: List[str] = Field(default_factory=list, description="RAG 知识库来源引用（纯文本）")
    source_details: List[SourceItem] = Field(default_factory=list, description="结构化来源元数据")
    turn_count: int = Field(default=0, description="当前对话轮次")


class ReportUploadResponse(BaseModel):
    report_id: str = Field(..., description="报告唯一标识")
    indicators: List[IndicatorItem] = Field(default_factory=list, description="提取到的检验指标")
    abnormal_count: int = Field(default=0)
    normal_count: int = Field(default=0)
    report_date: str = Field(default="", description="检验日期")
    ocr_mock: bool = Field(default=False, description="是否使用了内置 Mock OCR 数据")
    raw_ocr_text: str = Field(default="", description="OCR 原始识别文本")


class IndicatorItem(BaseModel):
    key: str = Field(..., description="标准化指标键名，如 'creatinine'")
    name: str = Field(..., description="中文名，如 '血肌酐'")
    value: float = Field(..., description="数值")
    unit: str = Field(default="", description="单位")
    ref_range: str = Field(default="", description="参考范围")
    status: str = Field(default="normal", description="normal / high / low")


class UserProfileRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一标识")
    name: str = Field(default="")
    age: int = Field(default=0, ge=0, le=150)
    gender: str = Field(default="", pattern=r"^(男|女|)$")
    medical_history: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    current_medications: List[str] = Field(default_factory=list)


class UserProfileResponse(BaseModel):
    user_id: str
    name: str
    age: int
    gender: str
    medical_history: List[str]
    allergies: List[str]
    current_medications: List[str]


class ErrorResponse(BaseModel):
    error: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(default=None, description="详细错误描述")
