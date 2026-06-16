"""
Agent 医疗专用工具集

每个工具接收 JSON 字符串参数，返回字符串结果。
工具设计原则：
- 单一职责，每个工具只做一件事
- 输入输出均为字符串（与 Tool 接口兼容）
- 返回结果可直接注入 Prompt 上下文
"""

from __future__ import annotations
import json
import logging
import sys
import os

logger = logging.getLogger(__name__)


def tool_reference_lookup(args_json: str) -> str:
    """
    查询检验指标的参考范围和临床意义

    参数：{"indicator": "creatinine", "age": 45, "gender": "男"}
    返回：参考范围文本
    """
    try:
        args = json.loads(args_json) if isinstance(args_json, str) else args_json
        indicator = args.get("indicator", "")
        age = int(args.get("age", 0))
        gender = args.get("gender", "")

        # 导入参考范围
        _harness = os.path.join(os.path.dirname(__file__), "..", "long_memory")
        if _harness not in sys.path:
            sys.path.insert(0, _harness)

        from knowledge.reference_ranges import REFERENCE_RANGES, format_reference_text

        # 尝试解析 key
        from app.business.indicator_classifier import _resolve_key, classify_indicator
        resolved = _resolve_key(indicator)

        if resolved in REFERENCE_RANGES:
            return format_reference_text(resolved)

        return f"未找到指标 '{indicator}' 的参考范围信息。可查询的指标包括：{', '.join(list(REFERENCE_RANGES.keys())[:20])}..."

    except Exception as e:
        return f"查询参考范围失败：{e}"


def tool_calculate_egfr(args_json: str) -> str:
    """
    计算 eGFR（估算肾小球滤过率），使用 CKD-EPI 公式

    参数：{"creatinine": 120, "age": 45, "gender": "男", "race": "asian"}
    返回：eGFR 值和 CKD 分期
    """
    try:
        args = json.loads(args_json) if isinstance(args_json, str) else args_json
        cr = float(args.get("creatinine", 0))
        age = int(args.get("age", 0))
        gender = args.get("gender", "男")
        race = args.get("race", "asian")

        if cr <= 0 or age <= 0:
            return "错误：肌酐值和年龄必须大于 0"

        # CKD-EPI 2021 公式（简化版，不包含种族因子）
        if gender == "女":
            kappa, alpha = 0.7, -0.241
            gender_factor = 1.012
        else:
            kappa, alpha = 0.9, -0.302
            gender_factor = 1.0

        cr_ratio = (cr / 88.4) / kappa  # μmol/L → mg/dL
        egfr = 142 * (min(cr_ratio, 1.0) ** alpha) * (max(cr_ratio, 1.0) ** -1.200) * (0.9938 ** age) * gender_factor

        # CKD 分期
        if egfr >= 90:
            stage = "G1（正常或高滤过）"
        elif egfr >= 60:
            stage = "G2（轻度下降）"
        elif egfr >= 45:
            stage = "G3a（轻中度下降）"
        elif egfr >= 30:
            stage = "G3b（中重度下降）"
        elif egfr >= 15:
            stage = "G4（重度下降）"
        else:
            stage = "G5（肾功能衰竭）"

        return (
            f"eGFR = {egfr:.1f} mL/min/1.73m²\n"
            f"CKD 分期：{stage}\n"
            f"计算方法：CKD-EPI 2021\n"
            f"输入参数：肌酐={cr} μmol/L, 年龄={age}岁, 性别={gender}"
        )

    except Exception as e:
        return f"计算 eGFR 失败：{e}"


def tool_search_knowledge(args_json: str) -> str:
    """
    从医学知识库检索相关内容（触发 RAG）

    参数：{"query": "慢性肾脏病饮食管理", "top_k": 3}
    返回：检索到的知识文本
    """
    try:
        args = json.loads(args_json) if isinstance(args_json, str) else args_json
        query = args.get("query", "")
        top_k = int(args.get("top_k", 3))

        if not query:
            return "错误：请提供检索关键词"

        _long_memory = os.path.join(os.path.dirname(__file__), "..", "long_memory")
        if _long_memory not in sys.path:
            sys.path.insert(0, _long_memory)

        from knowledge.rag import retrieve_medical_knowledge
        answer, docs = retrieve_medical_knowledge(query)

        if answer:
            return answer
        return f"未找到与 '{query}' 相关的医学知识。请尝试更具体的关键词。"

    except Exception as e:
        return f"知识检索失败：{e}"


def tool_analyze_indicator(args_json: str) -> str:
    """
    分析单个检验指标是否异常，返回详细判定结果

    参数：{"indicator": "creatinine", "value": 120, "age": 45, "gender": "男"}
    返回：异常状态、参考范围、临床意义
    """
    try:
        args = json.loads(args_json) if isinstance(args_json, str) else args_json
        indicator = args.get("indicator", "")
        value = float(args.get("value", 0))
        age = int(args.get("age", 0))
        gender = args.get("gender", "")

        from app.business.indicator_classifier import classify_indicator
        result = classify_indicator(indicator, value, age=age, gender=gender)

        return (
            f"指标名称：{result['name']}\n"
            f"检测值：{result['value']} {result['unit']}\n"
            f"参考范围：{result['ref_range']}\n"
            f"状态：{result['status']}\n"
            f"{'⚠️ 危急值！' if result['is_critical'] else ''}\n"
            f"临床意义：{result['description']}\n"
            f"年龄分组：{result['age_group']}"
        )

    except Exception as e:
        return f"指标分析失败：{e}"


# 工具注册表（供 create_agent 使用）
def get_default_tools() -> list:
    """获取默认医疗工具集"""
    from harness.llm_adapter.create_agent import Tool

    return [
        Tool(
            name="reference_lookup",
            description="查询检验指标的参考范围、临床意义。参数：indicator(指标英文名), age(年龄), gender(性别)",
            func=tool_reference_lookup,
        ),
        Tool(
            name="calculate_egfr",
            description="根据肌酐值、年龄、性别计算 eGFR 估算肾小球滤过率和 CKD 分期。参数：creatinine(肌酐值μmol/L), age(年龄), gender(性别)",
            func=tool_calculate_egfr,
        ),
        Tool(
            name="search_knowledge",
            description="从医学知识库检索专业医学知识。参数：query(检索问题), top_k(返回条数，默认3)",
            func=tool_search_knowledge,
        ),
        Tool(
            name="analyze_indicator",
            description="分析单个检验指标是否异常，返回详细判定结果。参数：indicator(指标英文名), value(数值), age(年龄), gender(性别)",
            func=tool_analyze_indicator,
        ),
    ]
