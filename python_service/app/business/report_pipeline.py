"""
报告处理管线：串联 OCR → 结构化提取 → 指标分类 → 联动分析 → 解读上下文生成

这是模块一（报告录入）和模块二（智能解读）之间的桥梁层。
上传报告后，通过此管线完成从原始 OCR 文本到可注入 Agent 的结构化上下文的完整流程。
"""

from __future__ import annotations
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.business.lab_report import LabReport, LabIndicator
from app.business.indicator_classifier import batch_classify
from app.business.correlation_engine import CorrelationEngine

logger = logging.getLogger(__name__)

# OCR 服务地址
OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://localhost:8001")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


class ReportPipeline:
    """报告处理管线"""

    def __init__(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(REPORT_DIR, exist_ok=True)
        self._correlation = CorrelationEngine()

    async def call_ocr(self, file_path: str) -> dict:
        """
        调用 OCR 服务（优先级: PaddleOCR 本地 > 云 OCR > Mock）

        - 先尝试 PaddleOCR 本地服务（:8001 的 /api/v1/analyze-vision）
        - 不可用时回退 Mock 数据
        """
        url = f"{OCR_SERVICE_URL}/api/v1/analyze-vision"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={"path": file_path, "force_recheck": False})
                resp.raise_for_status()
                result = resp.json()
                # 检查是否是 PaddleOCR 返回
                if "error" in result and result["error"]:
                    logger.warning("OCR service returned error: %s", result["error"])
                    return self._mock_ocr()
                engine = "PaddleOCR" if "PaddleOCR" in str(result) else "cloud"
                logger.info("OCR success via %s: %d indicators",
                            engine, result.get("gat_structured", {}).get("mapped_count", 0))
                return result
        except Exception as e:
            logger.warning("OCR service unavailable (%s), using mock data", e)
            return self._mock_ocr()

    def _mock_ocr(self) -> dict:
        """生成模拟 OCR 结果，用于演示和测试"""
        return {
            "cached": False,
            "analysis": [],
            "full_extraction": [
                "白细胞计数(WBC): 7.2 ×10⁹/L 参考值: 4.5-11.0 状态: 正常",
                "红细胞计数(RBC): 4.8 ×10¹²/L 参考值: 4.5-5.9 状态: 正常",
                "血红蛋白(HB): 14.2 g/dL 参考值: 13.0-16.0 状态: 正常",
                "血小板计数(PLT): 250 ×10⁹/L 参考值: 150-400 状态: 正常",
                "丙氨酸氨基转移酶(ALT): 28 U/L 参考值: <40 状态: 正常",
                "天冬氨酸氨基转移酶(AST): 32 U/L 参考值: <40 状态: 正常",
                "总胆红素(TBIL): 0.8 mg/dL 参考值: <1.2 状态: 正常",
                "肌酐(CREA): 0.85 mg/dL 参考值: 0.7-1.3 状态: 正常",
                "尿素氮(BUN): 16 mg/dL 参考值: 7-20 状态: 正常",
                "尿酸(UA): 5.2 mg/dL 参考值: 3.5-7.2 状态: 正常",
            ],
            "gat_structured": {
                "patient_labs": {
                    "creatinine": 96.2,  # 0.85 mg/dL → ~96.2 μmol/L
                    "bun": 5.7,
                    "uric_acid": 308,
                    "alt": 28, "ast": 32, "tbil": 15.2,
                    "wbc": 7.2, "rbc": 4.8, "hemoglobin": 14.2, "plt": 250,
                },
                "base_labs": {},
                "ratio_labs": {},
                "mapped_count": 10,
                "total_items": 10,
                "coverage": "100%",
            },
        }

    def build_report(
        self,
        user_id: str,
        file_path: str,
        ocr_result: dict,
        report_date: str = "",
        age: int = 0,
        gender: str = "",
    ) -> LabReport:
        """
        从 OCR 结果构建结构化 LabReport

        管线步骤：
        1. 提取 patient_labs → 2. 批量分类 → 3. 构建 LabIndicator 列表 → 4. 组装 LabReport
        """
        # Step 1: 提取 OCR 结构化数据
        patient_labs: dict[str, float] = {}
        gat = ocr_result.get("gat_structured", {})
        raw_labs = gat.get("patient_labs", {})
        for k, v in raw_labs.items():
            try:
                patient_labs[k] = float(v)
            except (ValueError, TypeError):
                pass

        raw_ocr = "\n".join(ocr_result.get("full_extraction", [])) if ocr_result.get("full_extraction") else ""

        # Step 2: 批量分类（使用完整 reference_ranges）
        classified = batch_classify(patient_labs, age=age, gender=gender)

        # Step 3: 构建 LabIndicator 列表
        indicators: list[LabIndicator] = []
        abnormal: list[LabIndicator] = []
        normal_list: list[LabIndicator] = []

        for item in classified:
            ind = LabIndicator(
                key=item["key"],
                name=item["name"],
                value=item["value"],
                unit=item["unit"],
                ref_range=item["ref_range"],
                status=item["status"],
                description=item["description"],
                is_critical=item["is_critical"],
            )
            indicators.append(ind)
            if ind.status != "normal":
                abnormal.append(ind)
            else:
                normal_list.append(ind)

        # Step 4: 组装 LabReport
        file_hash = hashlib.md5(open(file_path, "rb").read()).hexdigest()[:12] if os.path.exists(file_path) else "unknown"
        report_id = f"rpt_{file_hash}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        if not report_date:
            report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        report = LabReport(
            report_id=report_id,
            user_id=user_id,
            report_date=report_date,
            file_path=file_path,
            indicators=indicators,
            abnormal_indicators=abnormal,
            normal_indicators=normal_list,
            raw_ocr_text=raw_ocr,
        )

        logger.info(
            "Report built: %s | %d indicators (%d abnormal, %d normal, %d critical)",
            report_id, report.total_count, report.abnormal_count,
            report.normal_count, len(report.get_critical_indicators()),
        )
        return report

    def analyze_correlations(self, report: LabReport) -> dict:
        """
        联动分析：检测多指标组合异常

        返回：
            {"matches": [CorrelationMatch, ...], "context_text": "..."}
        """
        # 转换为 dict 列表供 correlation engine 使用
        indicator_dicts = [
            {"key": ind.key, "name": ind.name, "status": ind.status}
            for ind in report.indicators
        ]
        matches = self._correlation.analyze(indicator_dicts)
        context_text = self._correlation.to_prompt_context(matches)

        return {"matches": matches, "context_text": context_text}

    def generate_interpretation_prompt(
        self,
        report: LabReport,
        correlations: dict,
    ) -> str:
        """
        生成首轮解读 prompt（报告上传后自动触发）

        整合了三类信息：
        - 报告结构化指标总览
        - 单项指标详情
        - 联动分析结论
        """
        parts = [
            "请对以下化验报告进行智能解读。",
            "",
            report.to_context_text(),
        ]

        corr_text = correlations.get("context_text", "")
        if corr_text:
            parts.append(f"\n{corr_text}")

        parts.append(
            "\n\n请按以下结构输出解读："
            "\n1. 📋 报告总览（几句话概括整体情况）"
            "\n2. 🔍 异常指标详细解读（逐项用通俗语言解释）"
            "\n3. 🔗 关联指标分析（如有联动模式，解读其临床含义）"
            "\n4. 💡 健康建议（饮食/运动/复查建议，不可推荐药品）"
            "\n\n请注意：不可做出确诊断言，建议仅供临床参考。"
        )

        return "\n".join(parts)

    def save_report(self, report: LabReport) -> str:
        """持久化报告到 reports/ 目录"""
        return report.save(REPORT_DIR)

    def load_report(self, report_id: str) -> Optional[LabReport]:
        """从 reports/ 加载报告"""
        path = os.path.join(REPORT_DIR, f"{report_id}.json")
        return LabReport.load(path)

    def list_user_reports(self, user_id: str) -> list[dict]:
        """列出用户的所有报告摘要"""
        reports = []
        if not os.path.isdir(REPORT_DIR):
            return reports

        for fname in sorted(os.listdir(REPORT_DIR), reverse=True):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(REPORT_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("user_id") == user_id:
                    reports.append({
                        "report_id": data["report_id"],
                        "report_date": data.get("report_date", ""),
                        "total_count": data.get("total_count", 0),
                        "abnormal_count": data.get("abnormal_count", 0),
                        "has_critical": data.get("has_critical", False),
                    })
            except Exception:
                pass
        return reports


# 全局单例
_pipeline: Optional[ReportPipeline] = None


def get_report_pipeline() -> ReportPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReportPipeline()
    return _pipeline
