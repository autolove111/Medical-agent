import re
from typing import Dict, Optional

# 所有映射输出小写英文标准名称，保证与 OCR 的 _INDICATOR_ALIAS key 一致
_INDICATOR_ALIAS = {
    # ========== 中文医学名称 ==========
    "肌酐": "creatinine",
    "尿素氮": "bun",
    "尿酸": "uric_acid",
    "葡萄糖": "glucose",
    "白细胞": "wbc",
    "红细胞": "rbc",
    "血红蛋白": "hemoglobin",
    "羟丁酸脱氢酶": "a_hbd",
    "α-羟丁酸脱氢酶": "a_hbd",
    "a-羟丁酸脱氢酶": "a_hbd",
    "hbdh": "a_hbd",
    "血小板": "plt",
    "丙氨酸氨基转移酶": "alt",
    "天门冬氨酸氨基转移酶": "ast",
    
    # ========== OCR/英文小写（对应 OCR 的 _INDICATOR_ALIAS key）==========
    # 血细胞计数（保持小写）
    "wbc": "wbc",
    "rbc": "rbc",
    "hemoglobin": "hemoglobin",
    "hb": "hemoglobin",
    "hematocrit": "hematocrit",
    "hct": "hematocrit",
    "mcv": "mcv",
    "mch": "mch",
    "mchc": "mchc",
    "plt": "plt",
    "platelet": "plt",
    
    # 白细胞分类
    "ne": "ne",
    "ly": "ly",
    "mo": "mo",
    "eo": "eo",
    "ba": "ba",
    "nrbc": "nrbc",
    "rdw": "rdw",
    "mpv": "mpv",
    "pct": "pct",
    "pdw": "pdw",
    
    # 生化指标：代谢
    "glucose": "glucose",
    "glu": "glucose",
    "bun": "bun",
    "creatinine": "creatinine",
    "cr": "creatinine",
    "uric_acid": "uric_acid",
    "uric acid": "uric_acid",
    "ua": "uric_acid",
    
    # 生化指标：肝功能
    "alt": "alt",
    "ast": "ast",
    "alp": "alp",
    "alkaline_phosphatase": "alp",
    "ggt": "ggt",
    "gamma_glutamyl_transferase": "ggt",
    "total_bilirubin": "total_bilirubin",
    "tbil": "total_bilirubin",
    "direct_bilirubin": "direct_bilirubin",
    "dbil": "direct_bilirubin",
    
    # 生化指标：电解质
    "sodium": "sodium",
    "na": "sodium",
    "potassium": "potassium",
    "k": "potassium",
    "chloride": "chloride",
    "cl": "chloride",
    "calcium": "calcium",
    "ca": "calcium",
    "phosphorus": "phosphorus",
    "phosphate": "phosphorus",
    "p": "phosphorus",
    "magnesium": "magnesium",
    "mg": "magnesium",
    "po4": "phosphorus",
    
    # 生化指标：脂质
    "cholesterol": "cholesterol",
    "cho": "cholesterol",
    "triglyceride": "triglyceride",
    "tg": "triglyceride",
    
    # 蛋白质代谢
    "total_protein": "total_protein",
    "tp": "total_protein",
    "albumin": "albumin",
    "alb": "albumin",
    "globulin": "globulin",
    "glo": "globulin",
    "a_g_ratio": "a_g_ratio",
    "a/g": "a_g_ratio",
    "ag_ratio": "a_g_ratio",
    
    # 胆汁和肝脏
    "total_bile_acid": "total_bile_acid",
    "tba": "total_bile_acid",
    "cholinesterase": "cholinesterase",
    "che": "cholinesterase",
    
    # 心肌标志物
    "creatine_kinase": "creatine_kinase",
    "ck": "creatine_kinase",
    "ldh": "ldh",
    "lactic_dehydrogenase": "ldh",
    "a_hbd": "a_hbd",
    "alpha_hbd": "a_hbd",
    "hbd": "a_hbd",
    
    # 肾功能扩展
    "urea": "urea",
    "cystatin_c": "cystatin_c",
    "cystatin": "cystatin_c",
    "cys_c": "cystatin_c",
    
    # 酸碱平衡
    "co2": "co2",
    "bicarbonate": "co2",
    
    # 兼容项
    "egfr": "egfr",
    "hba1c": "hba1c",
}


def extract_numeric_value(raw_value) -> Optional[float]:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if not isinstance(raw_value, str):
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", raw_value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


def normalize_indicator_key(raw_name: str) -> Optional[str]:
    if not raw_name:
        return None

    alias = _INDICATOR_ALIAS.get(raw_name.strip())
    if alias:
        return alias

    lowered = raw_name.lower()
    if "hbdh" in lowered or "羟丁酸脱氢酶" in raw_name:
        return "HBDH"

    bracket_match = re.search(r"\(([A-Za-z]{2,8})\)", raw_name)
    if bracket_match:
        return bracket_match.group(1).upper()

    ascii_key = re.sub(r"[^A-Za-z0-9]", "", raw_name).upper()
    if 2 <= len(ascii_key) <= 8:
        return ascii_key
    return None


def is_plausible_lab_value(indicator: str, value: float) -> bool:
    """验证检验值是否在合理范围内"""
    plausible_ranges = {
        # 血细胞计数
        "hemoglobin": (40, 250),
        "hb": (40, 250),
        "rbc": (1, 10),
        "wbc": (0.1, 100),
        "plt": (1, 1500),
        "hematocrit": (0.1, 100),
        "hct": (0.1, 100),
        
        # 肾功能
        "creatinine": (5, 2000),
        "cr": (5, 2000),
        "urea": (1, 100),
        "bun": (0.5, 80),
        "uric_acid": (10, 1000),
        "ua": (10, 1000),
        "cystatin_c": (0.3, 5),
        
        # 肝功能
        "alt": (0, 500),
        "ast": (0, 500),
        "alp": (0, 400),
        "ggt": (0, 400),
        "total_bilirubin": (0, 500),
        "tbil": (0, 500),
        "direct_bilirubin": (0, 300),
        "dbil": (0, 300),
        "total_protein": (40, 120),
        "tp": (40, 120),
        "albumin": (20, 80),
        "alb": (20, 80),
        "globulin": (15, 50),
        "glo": (15, 50),
        
        # 代谢
        "glucose": (1, 50),
        "glu": (1, 50),
        "cholesterol": (0, 20),
        "cho": (0, 20),
        "triglyceride": (0, 50),
        "tg": (0, 50),
        
        # 电解质
        "sodium": (100, 160),
        "na": (100, 160),
        "potassium": (1, 10),
        "k": (1, 10),
        "chloride": (70, 120),
        "cl": (70, 120),
        "calcium": (1, 5),
        "ca": (1, 5),
        "phosphorus": (0.5, 3),
        "p": (0.5, 3),
        "magnesium": (0.5, 3),
        "mg": (0.5, 3),
        "co2": (5, 50),
        
        # 心肌指标
        "creatine_kinase": (0, 500),
        "ck": (0, 500),
        "ldh": (0, 500),
        "a_hbd": (0, 400),
    }
    rr = plausible_ranges.get(indicator)
    if not rr:
        return True  # 如果没定义范围，认为合理
    low, high = rr
    return low <= value <= high


def extract_lab_results(ocr_result: Optional[Dict]) -> Dict[str, float]:
    if not ocr_result:
        return {}

    gat_structured = ocr_result.get("gat_structured")
    if isinstance(gat_structured, dict):
        patient_labs = gat_structured.get("patient_labs")
        if isinstance(patient_labs, dict):
            normalized: Dict[str, float] = {}
            for raw_key, raw_value in patient_labs.items():
                value = extract_numeric_value(raw_value)
                if value is None:
                    continue
                key = normalize_indicator_key(str(raw_key)) or str(raw_key).strip()
                if not is_plausible_lab_value(key, value):
                    continue
                normalized[key] = value
            if normalized:
                return normalized

    direct_results = ocr_result.get("lab_results")
    if isinstance(direct_results, dict):
        normalized: Dict[str, float] = {}
        for raw_key, raw_value in direct_results.items():
            value = extract_numeric_value(raw_value)
            if value is None:
                continue
            key = normalize_indicator_key(str(raw_key)) or str(raw_key).strip()
            if not is_plausible_lab_value(key, value):
                continue
            normalized[key] = value
        return normalized

    analysis_items = ocr_result.get("analysis")
    if not isinstance(analysis_items, list):
        return {}

    results: Dict[str, float] = {}
    for item in analysis_items:
        if not isinstance(item, dict):
            continue

        raw_name = str(
            item.get("indicator")
            or item.get("item")
            or item.get("name")
            or item.get("test_name")
            or ""
        ).strip()
        value = extract_numeric_value(item.get("value") or item.get("result"))
        if not raw_name or value is None:
            continue

        key = normalize_indicator_key(raw_name) or raw_name
        if not is_plausible_lab_value(key, value):
            continue
        results[key] = value

    return results
