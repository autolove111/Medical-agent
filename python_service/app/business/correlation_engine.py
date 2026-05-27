"""
多指标联动规则引擎

检测化验报告中多个相关指标的组合异常，生成关联解读触发信号。
这是模块二「总体解读」的核心能力——不作单一指标判断，而是发现指标间的联动模式。

每条规则包含：
- 名称、触发条件（多指标异常组合）、严重程度、RAG 检索建议、自然语言描述模板
"""

from __future__ import annotations
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class CorrelationMatch:
    """一条匹配成功的联动规则"""
    name: str                                   # 规则名称，如 "肾功能受损信号"
    severity: str                               # high / medium / low
    matched_indicators: list[str]               # 触发该规则的具体指标
    description: str                            # 自然语言描述
    rag_query: str                              # 建议的 RAG 检索 query
    suggestion_hint: str = ""                   # 给用户的行动建议提示


# 多指标联动规则库（可按需扩展）
CORRELATION_RULES: list[dict] = [
    # ===== 肾功能 =====
    {
        "name": "肾功能受损信号",
        "severity": "high",
        "conditions": [
            {"key": "creatinine", "status": "high"},
            {"key": "bun", "status": "high"},
        ],
        "description": (
            "血肌酐和尿素氮同时升高是肾功能下降的典型信号。"
            "肌酐反映肾小球滤过功能，尿素氮反映肾脏清除代谢废物的能力，"
            "两者同时异常提示肾脏可能已受到一定程度的损伤。"
        ),
        "rag_query": "肾功能不全 血肌酐升高 尿素氮升高 CKD分期",
        "suggestion_hint": "建议尽快到肾内科就诊，完善 eGFR 和尿微量白蛋白检查。",
    },
    {
        "name": "严重肾功能损害",
        "severity": "high",
        "conditions": [
            {"key": "creatinine", "status": "high"},
            {"key": "bun", "status": "high"},
            {"key": "uric_acid", "status": "high"},
        ],
        "description": (
            "血肌酐、尿素氮和尿酸三项同时升高，提示肾功能显著下降。"
            "尿酸升高可能是肾脏排泄障碍所致，需警惕痛风或肾结石风险。"
        ),
        "rag_query": "慢性肾衰竭 高尿酸血症 肾功能三项异常",
        "suggestion_hint": "建议尽快到肾内科就诊，避免使用肾毒性药物。",
    },
    {
        "name": "蛋白尿+肾功能下降（CKD 高风险）",
        "severity": "high",
        "conditions": [
            {"key": "creatinine", "status": "high"},
            {"key": "albumin", "status": "low"},
        ],
        "description": (
            "血肌酐升高同时白蛋白降低，是慢性肾脏病(CKD)的典型表现。"
            "白蛋白降低提示蛋白质从尿液中流失（蛋白尿），合并肾功能下降，"
            "需高度警惕 CKD 进展。"
        ),
        "rag_query": "CKD 白蛋白降低 肌酐升高 蛋白尿 慢性肾脏病",
        "suggestion_hint": "建议检测尿常规+尿微量白蛋白/肌酐比值(UACR)，肾内科随访。",
    },

    # ===== 肝功能 =====
    {
        "name": "肝细胞损伤信号",
        "severity": "high",
        "conditions": [
            {"key": "alt", "status": "high"},
            {"key": "ast", "status": "high"},
        ],
        "description": (
            "ALT 和 AST 同时升高是肝细胞受损的直接标志。"
            "ALT 主要存在于肝细胞内，AST 分布于肝脏和心肌。"
            "ALT/AST 比值有助于判断肝损伤类型。"
        ),
        "rag_query": "转氨酶升高 肝功能损伤 ALT AST 比值",
        "suggestion_hint": "建议避免饮酒，尽快到消化内科检查。",
    },
    {
        "name": "胆汁淤积型肝损伤",
        "severity": "high",
        "conditions": [
            {"key": "alt", "status": "high"},
            {"key": "tbil", "status": "high"},
        ],
        "description": (
            "ALT 和总胆红素同时升高，提示肝细胞损伤伴有胆汁排泄障碍。"
            "常见于药物性肝损伤、病毒性肝炎或胆道梗阻。"
        ),
        "rag_query": "胆汁淤积 胆红素升高 ALT升高 肝损伤",
        "suggestion_hint": "建议查直接胆红素、GGT、ALP 以鉴别诊断。",
    },
    {
        "name": "酒精性肝病倾向",
        "severity": "medium",
        "conditions": [
            {"key": "ast", "status": "high"},
            {"key": "ggt", "status": "high"},
        ],
        "description": (
            "AST 和 GGT 同时升高是酒精性肝病的典型实验室特征。"
            "GGT 对酒精摄入特别敏感，AST/ALT 比值 > 2 高度提示酒精性因素。"
        ),
        "rag_query": "酒精性肝病 GGT升高 AST升高 戒酒 肝功能恢复",
        "suggestion_hint": "严格戒酒，定期复查肝功能。",
    },

    # ===== 代谢综合征 =====
    {
        "name": "代谢综合征（三高倾向）",
        "severity": "high",
        "conditions": [
            {"key": "glucose", "status": "high"},
            {"key": "cholesterol", "status": "high"},
            {"key": "triglyceride", "status": "high"},
        ],
        "description": (
            "血糖、胆固醇、甘油三酯三项同时偏高，高度提示代谢综合征。"
            "这是心血管疾病和 2 型糖尿病的重要危险因素。"
        ),
        "rag_query": "代谢综合征 高血糖 高血脂 饮食运动管理",
        "suggestion_hint": "建议控制饮食总热量，增加有氧运动，内分泌科就诊。",
    },
    {
        "name": "糖尿病肾病早期信号",
        "severity": "high",
        "conditions": [
            {"key": "glucose", "status": "high"},
            {"key": "creatinine", "status": "high"},
        ],
        "description": (
            "血糖和血肌酐同时升高需警惕糖尿病肾病。"
            "长期高血糖可损害肾小球微血管，导致肾功能逐渐下降。"
        ),
        "rag_query": "糖尿病肾病 高血糖 血肌酐升高 防治",
        "suggestion_hint": "建议检测 HbA1c 和尿微量白蛋白，强化血糖控制。",
    },

    # ===== 贫血 =====
    {
        "name": "低色素性贫血（缺铁性贫血可能）",
        "severity": "medium",
        "conditions": [
            {"key": "hemoglobin", "status": "low"},
            {"key": "mcv", "status": "low"},
        ],
        "description": (
            "血红蛋白降低伴 MCV 减小是典型的小细胞低色素性贫血表现，"
            "最常见原因是缺铁。需结合血清铁、铁蛋白进一步判断。"
        ),
        "rag_query": "缺铁性贫血 血红蛋白低 MCV低 饮食补铁",
        "suggestion_hint": "建议增加红肉、动物肝脏等富铁食物摄入，血液科就诊。",
    },
    {
        "name": "大细胞性贫血（叶酸/B12缺乏可能）",
        "severity": "medium",
        "conditions": [
            {"key": "hemoglobin", "status": "low"},
            {"key": "mcv", "status": "high"},
        ],
        "description": (
            "血红蛋白降低伴 MCV 增大提示巨幼细胞性贫血，"
            "常见原因是叶酸或维生素 B12 缺乏。"
        ),
        "rag_query": "巨幼细胞性贫血 MCV高 叶酸缺乏 维生素B12",
        "suggestion_hint": "建议检测血清叶酸和维生素 B12 水平。",
    },

    # ===== 炎症/感染 =====
    {
        "name": "细菌感染信号",
        "severity": "medium",
        "conditions": [
            {"key": "wbc", "status": "high"},
            {"key": "ne", "status": "high"},
        ],
        "description": (
            "白细胞总数升高伴中性粒细胞比例增高，是细菌感染的典型血象表现。"
            "中性粒细胞是抵抗细菌感染的第一道防线。"
        ),
        "rag_query": "白细胞升高 中性粒细胞升高 细菌感染",
        "suggestion_hint": "结合发热、咳嗽等症状判断感染部位，必要时抗生素治疗。",
    },
    {
        "name": "严重感染/脓毒症倾向",
        "severity": "high",
        "conditions": [
            {"key": "wbc", "status": "high"},
            {"key": "ne", "status": "high"},
            {"key": "crp", "status": "high"},
        ],
        "description": (
            "白细胞升高+中性粒细胞升高+CRP 升高三联征，提示较严重的感染或炎症状态。"
            "CRP 是急性时相蛋白，显著升高需警惕脓毒症风险。"
        ),
        "rag_query": "脓毒症 白细胞升高 CRP升高 感染严重程度评估",
        "suggestion_hint": "建议立即就医，完善血培养和 PCT 检测。",
    },

    # ===== 电解质 =====
    {
        "name": "电解质紊乱（低钾+低钠）",
        "severity": "medium",
        "conditions": [
            {"key": "potassium", "status": "low"},
            {"key": "sodium", "status": "low"},
        ],
        "description": (
            "钾和钠同时降低常见于呕吐、腹泻、利尿剂使用后。"
            "严重低钾可影响心脏传导，需及时纠正。"
        ),
        "rag_query": "低钾血症 低钠血症 电解质紊乱 补钾",
        "suggestion_hint": "建议增加含钾食物（香蕉、土豆），复查电解质。",
    },

    # ===== 肾性贫血 =====
    {
        "name": "肾性贫血（CKD 并发症）",
        "severity": "high",
        "conditions": [
            {"key": "creatinine", "status": "high"},
            {"key": "hemoglobin", "status": "low"},
        ],
        "description": (
            "肾功能下降合并贫血是慢性肾脏病的常见并发症。"
            "肾脏产生的促红细胞生成素(EPO)减少导致贫血，"
            "贫血反过来加重肾脏缺氧，形成恶性循环。"
        ),
        "rag_query": "肾性贫血 慢性肾脏病 EPO 贫血治疗 CKD",
        "suggestion_hint": "建议检测铁蛋白和 EPO 水平，肾内科评估是否需要促红细胞生成素治疗。",
    },

    # ===== 血脂代谢异常 =====
    {
        "name": "高胆固醇+高LDL（动脉粥样硬化风险）",
        "severity": "medium",
        "conditions": [
            {"key": "cholesterol", "status": "high"},
            {"key": "ldl", "status": "high"},
        ],
        "description": (
            "总胆固醇和低密度脂蛋白(LDL)同时升高是动脉粥样硬化的核心危险因素。"
            "LDL 是'坏胆固醇'，容易沉积在血管壁形成斑块。"
        ),
        "rag_query": "高胆固醇血症 LDL升高 动脉粥样硬化 降脂治疗",
        "suggestion_hint": "建议低脂饮食，增加运动，3个月后复查血脂。",
    },
]


class CorrelationEngine:
    """联动规则引擎"""

    def __init__(self, rules: list[dict] | None = None):
        self._rules = rules or CORRELATION_RULES

    def analyze(self, indicators: list[dict]) -> list[CorrelationMatch]:
        """
        分析一组指标，检测所有匹配的联动规则

        参数：
            indicators: classify_indicator() 返回的指标列表
                       每项含 key、status 字段

        返回：按严重程度排序的匹配规则列表
        """
        # 构建快速查找表：{key_lower: status}
        status_map: dict[str, str] = {}
        for ind in indicators:
            key_lower = ind["key"].lower()
            status_map[key_lower] = ind["status"]

        matches: list[CorrelationMatch] = []

        for rule in self._rules:
            all_met = True
            matched_keys: list[str] = []
            for cond in rule["conditions"]:
                cond_key = cond["key"].lower()
                actual_status = status_map.get(cond_key, "normal")
                required_status = cond["status"]

                # 匹配逻辑：required=high 时，actual 为 high 或 critical_high 都算匹配
                if required_status == "high" and actual_status in ("high", "critical_high"):
                    matched_keys.append(cond["key"])
                elif required_status == "low" and actual_status in ("low", "critical_low"):
                    matched_keys.append(cond["key"])
                else:
                    all_met = False
                    break

            if all_met and matched_keys:
                matches.append(CorrelationMatch(
                    name=rule["name"],
                    severity=rule["severity"],
                    matched_indicators=matched_keys,
                    description=rule["description"],
                    rag_query=rule["rag_query"],
                    suggestion_hint=rule.get("suggestion_hint", ""),
                ))

        # 按严重程度排序
        severity_order = {"high": 0, "medium": 1, "low": 2}
        matches.sort(key=lambda m: severity_order.get(m.severity, 3))
        return matches

    def to_prompt_context(self, matches: list[CorrelationMatch]) -> str:
        """将联动分析结果转为可注入 prompt 的文本"""
        if not matches:
            return ""

        lines = ["【多指标联动分析】"]
        for i, m in enumerate(matches, 1):
            flag = "🔴" if m.severity == "high" else "🟡" if m.severity == "medium" else "🟢"
            lines.append(f"\n{flag} 模式 {i}：{m.name}")
            lines.append(f"   关联指标：{', '.join(m.matched_indicators)}")
            lines.append(f"   解读：{m.description}")
            if m.suggestion_hint:
                lines.append(f"   行动建议：{m.suggestion_hint}")

        return "\n".join(lines)
