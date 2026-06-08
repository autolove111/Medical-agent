"""
解读引擎：结构化医学解读生成

核心职责：
- 接收 LabReport → 生成结构化解读 Prompt
- 为每个异常指标构建通俗解读引导（含 RAG 知识注入）
- 联动规则解读引导
- 饮食/运动建议生成
- 来源引用追踪与格式化

注意：真正的自然语言解读由 LLM 生成，此引擎负责构建最优 Prompt 结构。
"""

from __future__ import annotations
import logging
from typing import Optional

from app.business.lab_report import LabReport, LabIndicator
from app.business.source_tracker import SourceTracker, Citation
from app.business.dietary_advisor import DietaryAdvisor
from app.business.correlation_engine import CorrelationEngine

logger = logging.getLogger(__name__)


class InterpretationEngine:
    """医学解读引擎：构建结构化解读 Prompt"""

    def __init__(self):
        self._diet_advisor = DietaryAdvisor()
        self._correlation = CorrelationEngine()
        self._source_tracker = SourceTracker()

    def build_interpretation_prompt(
        self,
        report: LabReport,
        rag_answer: str = "",
        rag_docs: list | None = None,
    ) -> dict:
        """
        构建完整的解读 Prompt

        参数：
            report:    结构化化验报告
            rag_answer: RAG 检索到的知识文本（已有格式：含【来源】标记）
            rag_docs:   RAG 返回的原始 Document 列表

        返回：
            {
                "prompt": str,              # 完整的解读 Prompt
                "source_block": str,         # 来源引用块（注入 prompt）
                "sources": list[dict],       # 前端可渲染的来源列表
                "diet_block": str,           # 饮食建议块
                "exercise_block": str,       # 运动建议块
                "abnormal_count": int,
                "correlation_count": int,
            }
        """
        # Step 1: 收集异常指标 key
        abnormal_keys = [ind.key for ind in report.abnormal_indicators]

        # Step 2: 收集 RAG 来源
        self._source_tracker = SourceTracker()
        if rag_docs:
            self._source_tracker.add_from_rag_docs(rag_docs, category="indicator", indicator_keys=abnormal_keys)

        # Step 3: 联动分析
        indicator_dicts = [
            {"key": ind.key, "name": ind.name, "status": ind.status}
            for ind in report.indicators
        ]
        corr_matches = self._correlation.analyze(indicator_dicts)
        corr_context = self._correlation.to_prompt_context(corr_matches)

        # 为联动分析添加引用标记
        for m in corr_matches:
            self._source_tracker.add_manual(
                source_name="多指标联动规则引擎",
                excerpt=f"{m.name}: {m.description[:100]}",
                category="correlation",
                indicator_keys=m.matched_indicators,
            )

        # Step 4: 饮食/运动建议
        diet_block = self._diet_advisor.generate_diet_section(abnormal_keys)
        exercise_block = self._diet_advisor.generate_exercise_section(abnormal_keys)

        for a in self._diet_advisor.get_advice_for_indicators(abnormal_keys):
            self._source_tracker.add_manual(
                source_name=a.source,
                excerpt=a.detail[:100],
                category=a.category,
                indicator_keys=a.target_indicators,
            )

        # Step 5: 组装完整 Prompt
        prompt = self._assemble_prompt(
            report=report,
            rag_answer=rag_answer,
            corr_context=corr_context,
            diet_block=diet_block,
            exercise_block=exercise_block,
        )

        return {
            "prompt": prompt,
            "source_block": self._source_tracker.to_prompt_block(),
            "sources": self._source_tracker.to_api_list(),
            "diet_block": diet_block,
            "exercise_block": exercise_block,
            "abnormal_count": report.abnormal_count,
            "correlation_count": len(corr_matches),
            "total_sources": self._source_tracker.source_count,
            "unique_sources": self._source_tracker.unique_sources,
        }

    def _assemble_prompt(
        self,
        report: LabReport,
        rag_answer: str,
        corr_context: str,
        diet_block: str,
        exercise_block: str,
    ) -> str:
        """组装最终解读 Prompt"""

        parts = [
            "你是一个专业的医疗检验助手，请对以下化验报告进行详细解读。",
            "",
            "【解读要求】",
            "1. 用通俗易懂的语言解释每个异常指标的含义",
            "2. 如果存在多指标联动模式，请分析其临床意义",
            "3. 给出饮食和运动方面的健康建议",
            "4. 在每条关键信息后标注来源（如：参考[肾脏医学指南]）",
            "",
            "【红线约束 — 严格遵守】",
            '- 不可做出任何确诊断言（不能说"您已确诊XX病"）',
            "- 不可推荐具体药物品牌或剂量",
            '- 解读末尾必须注明"本建议仅供临床参考，不构成诊断"',
            "",
            "---",
            "",
            report.to_context_text(),
        ]

        # RAG 知识注入
        if rag_answer:
            parts.append("")
            parts.append("---")
            parts.append("【医学知识库参考】以下是从权威医学资源中检索到的知识，请优先参考：")
            parts.append(rag_answer)

        # 联动分析
        if corr_context:
            parts.append("")
            parts.append("---")
            parts.append(corr_context)

        # 饮食建议
        if diet_block:
            parts.append("")
            parts.append("---")
            parts.append(diet_block)

        # 运动建议
        if exercise_block:
            parts.append("")
            parts.append("---")
            parts.append(exercise_block)

        # 输出格式
        parts.append("")
        parts.append("---")
        parts.append("【输出格式】严格按以下结构回复，免责声明后立即停止：")
        parts.append("1. 报告总览（2-3 句话）")
        parts.append("2. 异常指标逐项解读")
        parts.append("3. 关联分析")
        parts.append("4. 健康管理建议（饮食+运动+复查）")
        parts.append("5. 参考来源")
        parts.append("6. 免责声明：本建议仅供临床参考，不构成诊断。请以主治医生医嘱为准。")
        parts.append("")
        parts.append("【严格禁止】免责声明之后不得添加任何话题标签(#)、社交媒体文案或互动引导语。回复必须在免责声明处结束。")

        return "\n".join(parts)


# 全局单例
_engine: Optional[InterpretationEngine] = None


def get_interpretation_engine() -> InterpretationEngine:
    global _engine
    if _engine is None:
        _engine = InterpretationEngine()
    return _engine
