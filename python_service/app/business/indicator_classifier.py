"""
指标分类器：对接 reference_ranges.py 的 40+ 种检验指标完整参考范围

核心职责：
- 根据指标 key、数值、年龄、性别，精确判定 normal / high / low / critical
- 匹配年龄分层（pediatric / child / adolescent / adult / elderly）
- 匹配性别差异（male / female）
- 检测危急值（critical_low / critical_high）
- 生成指标描述文本
"""

from __future__ import annotations
import sys
import os
from typing import Optional

# 确保能导入 harness/memory/knowledge 下的模块 (zly_3 已迁移路径)
_HARNESS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "harness", "memory")
if _HARNESS_ROOT not in sys.path:
    sys.path.insert(0, _HARNESS_ROOT)

from knowledge.reference_ranges import REFERENCE_RANGES, get_reference_range

# ---- OCR key → 参考范围 key 别名映射 ----
# OCR 服务返回的 key 是描述性小写英文，reference_ranges 使用简短大写缩写
_KEY_ALIAS: dict[str, str] = {
    "creatinine":    "Cr",
    "crea":          "Cr",
    "bun":           "BUN",
    "urea":          "UREA",
    "uric_acid":     "UA",
    "ua":            "UA",
    "glucose":       "GLU",
    "glu":           "GLU",
    "hba1c":         "HbA1c",
    "hemoglobin":    "HB",
    "hb":            "HB",
    "hgb":           "HB",
    "hematocrit":    "HCT",
    "hct":           "HCT",
    "wbc":           "WBC",
    "rbc":           "RBC",
    "plt":           "PLT",
    "alt":           "ALT",
    "ast":           "AST",
    "ggt":           "GGT",
    "alp":           "ALP",
    "total_bilirubin": "TBIL",
    "tbil":          "TBIL",
    "direct_bilirubin": "DBIL",
    "dbil":          "DBIL",
    "total_protein": "TP",
    "tp":            "TP",
    "albumin":       "ALB",
    "alb":           "ALB",
    "globulin":      "GLO",
    "glo":           "GLO",
    "a_g_ratio":     "A/G",
    "cholesterol":   "CHOL",
    "cho":           "CHOL",
    "triglyceride":  "TG",
    "tg":            "TG",
    "hdl":           "HDL",
    "ldl":           "LDL",
    "sodium":        "Na",
    "na":            "Na",
    "potassium":     "K",
    "k":             "K",
    "chloride":      "Cl",
    "cl":            "Cl",
    "calcium":       "Ca",
    "ca":            "Ca",
    "magnesium":     "Mg",
    "mg":            "Mg",
    "phosphorus":    "P",
    "phosphate":     "PO4",
    "mcv":           "MCV",
    "mch":           "MCH",
    "mchc":          "MCHC",
    "rdw":           "RDW",
    "mpv":           "MPV",
    "pct":           "PCT",
    "pdw":           "PDW",
    "ne":            "NE",
    "ly":            "LY",
    "mo":            "MO",
    "eo":            "EO",
    "ba":            "BA",
    "ck":            "CK",
    "ck_mb":         "CK-MB",
    "ldh":           "LDH",
    "troponin":      "Troponin",
    "bnp":           "BNP",
    "tsh":           "TSH",
    "t3":            "T3",
    "t4":            "T4",
    "crp":           "CRP",
    "tba":           "TBA",
    "che":           "CHE",
    "cystatin_c":    "CysC",
    "cysc":          "CysC",
    "co2":           "CO2",
    "egfr":          "eGFR",
}


def _resolve_key(key: str) -> str:
    """将 OCR key 解析为标准参考范围 key"""
    # 直接匹配
    if key in REFERENCE_RANGES:
        return key
    # 别名匹配
    lower = key.lower().strip()
    if lower in _KEY_ALIAS:
        resolved = _KEY_ALIAS[lower]
        if resolved in REFERENCE_RANGES:
            return resolved
    # 大写匹配
    upper = key.upper()
    if upper in REFERENCE_RANGES:
        return upper
    return key  # 无法解析，原样返回


# 年龄分组 → 参考范围 key 映射
_AGE_GROUP_ORDER = [
    ("infant", 1),       # 0-1 岁
    ("pediatric", 5),    # 1-5 岁
    ("child", 12),       # 5-12 岁
    ("adolescent", 18),  # 12-18 岁
    ("teen", 18),        # 同上
    ("adult", 60),       # 18-60 岁
    ("elderly", 120),    # 60+
    ("geriatric", 120),  # 同上
    ("senior", 120),     # 同上
]


def _age_group(age: int) -> str:
    """根据年龄返回对应的参考范围分组 key"""
    if age <= 0:
        return "adult"
    for group, threshold in _AGE_GROUP_ORDER:
        if age < threshold:
            return group
    return "adult"


def classify_indicator(
    key: str,
    value: float,
    age: int = 0,
    gender: str = "",
) -> dict:
    """
    分类单个指标，返回完整的判定结果

    参数：
        key:    标准化指标键名，如 "creatinine"、"Cr"、"CREA"
        value:  数值
        age:    年龄（0 表示未知，使用 adult 默认值）
        gender: 性别（"男" / "女"，空字符串忽略性别差异）

    返回：{
        "key", "name", "value", "unit", "status", "ref_range",
        "description", "is_critical", "age_group"
    }
    """
    resolved = _resolve_key(key)
    ref = get_reference_range(resolved)
    if not ref:
        return {
            "key": key, "name": key, "value": value, "unit": "",
            "status": "normal", "ref_range": "", "description": "",
            "is_critical": False, "age_group": "",
        }

    # 确定年龄分组
    group = _age_group(age)

    # 优先匹配性别 + 年龄分层的参考区间
    lo = None
    hi = None

    # 优先级 1: 性别特定范围
    if gender and gender in ref:
        lo = ref[gender].get("min")
        hi = ref[gender].get("max")

    # 优先级 2: 年龄分层范围
    if lo is None and group in ref:
        lo = ref[group].get("min")
        hi = ref[group].get("max")

    # 优先级 3: adult 范围
    if lo is None and "adult" in ref:
        lo = ref["adult"].get("min")
        hi = ref["adult"].get("max")

    # 优先级 4: normal 范围
    if lo is None and "normal" in ref:
        lo = ref["normal"].get("min")
        hi = ref["normal"].get("max")

    # 优先级 5: male 或 female（降级）
    if lo is None and "male" in ref:
        lo = ref["male"].get("min")
        hi = ref["male"].get("max")

    # 判定状态
    status = "normal"
    is_critical = False
    critical_high = ref.get("critical_high")
    critical_low = ref.get("critical_low")

    if critical_high is not None and value >= critical_high:
        status = "critical_high"
        is_critical = True
    elif critical_low is not None and value <= critical_low:
        status = "critical_low"
        is_critical = True
    elif hi is not None and value > hi:
        status = "high"
    elif lo is not None and value < lo:
        status = "low"

    # 构建参考范围文本
    unit = ref.get("unit", "")
    if lo is not None and hi is not None:
        ref_range = f"{lo}-{hi} {unit}".strip()
    elif lo is not None:
        ref_range = f"> {lo} {unit}".strip()
    elif hi is not None:
        ref_range = f"< {hi} {unit}".strip()
    else:
        ref_range = ""

    return {
        "key": key,
        "name": ref.get("name", key),
        "value": value,
        "unit": unit,
        "status": status,
        "ref_range": ref_range,
        "description": ref.get("description", ""),
        "is_critical": is_critical,
        "age_group": group,
    }


def batch_classify(
    patient_labs: dict[str, float],
    age: int = 0,
    gender: str = "",
) -> list[dict]:
    """
    批量分类多个指标

    参数：
        patient_labs: {key: value} 字典，如 {"creatinine": 120, "bun": 8.5}
        age: 年龄
        gender: 性别

    返回：按异常程度排序的指标列表（危急 > 异常 > 正常）
    """
    results = []
    for key, value in patient_labs.items():
        # 通过别名解析
        resolved = _resolve_key(key)
        if resolved in REFERENCE_RANGES:
            result = classify_indicator(resolved, float(value), age, gender)
            result["key"] = key  # 保留原始 key

        if result is None:
            # 未匹配参考范围，标记为 normal 但无描述
            result = {
                "key": key, "name": key, "value": float(value), "unit": "",
                "status": "normal", "ref_range": "", "description": "",
                "is_critical": False, "age_group": "",
            }
        results.append(result)

    # 排序：危急 → 高 → 低 → 正常
    severity = {
        "critical_high": 0, "critical_low": 1,
        "high": 2, "low": 3, "normal": 4,
    }
    results.sort(key=lambda r: severity.get(r["status"], 5))
    return results
