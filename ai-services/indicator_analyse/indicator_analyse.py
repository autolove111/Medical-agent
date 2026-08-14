"""
指标分析器 - 解析原始 Markdown + 对比参考范围，判断指标状态

职责：
  - 接收原始 Markdown（来自 MinerU OCR）
  - 解析表格，提取 patient_labs 字典
  - 对比 reference_ranges.py 中的参考范围
  - 判断每个指标的状态（normal/high/low/critical）
  - 返回符合前端 IndicatorItem 格式的列表

使用示例：
  patient_labs = parse_markdown_to_patient_labs(raw_markdown)
  indicators = analyze_indicators(patient_labs, age=31, gender="male")
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("indicator_analyse")

# ── 导入参考范围数据库 ──────────────────────────────────────────
try:
    from memory.knowledge.reference_ranges import REFERENCE_RANGES, get_reference_range
except ImportError:
    try:
        # 尝试备用路径
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from memory.knowledge.reference_ranges import REFERENCE_RANGES, get_reference_range
    except ImportError:
        # 如果导入失败，使用简化版本
        logger.warning("无法导入 reference_ranges，使用内置参考范围")
        REFERENCE_RANGES = {}
        def get_reference_range(key: str, age: int = 0, gender: str = "") -> Optional[dict]:
            return REFERENCE_RANGES.get(key)


# ── 指标别名映射（OCR key → 参考范围 key）─────────────────────────
_KEY_ALIAS = {
    "creatinine": "Cr", "crea": "Cr", "creat": "Cr",
    "bun": "BUN", "urea": "BUN",
    "uric_acid": "UA", "ua": "UA",
    "glucose": "GLU", "glu": "GLU",
    "hemoglobin": "HB", "hb": "HB", "hgb": "HB",
    "hematocrit": "HCT", "hct": "HCT",
    "wbc": "WBC", "rbc": "RBC", "plt": "PLT",
    "alt": "ALT", "ast": "AST", "ggt": "GGT", "alp": "ALP",
    "tbil": "TBIL", "dbil": "DBIL",
    "total_protein": "TP", "tp": "TP",
    "albumin": "ALB", "alb": "ALB",
    "triglyceride": "TG", "tg": "TG",
    "cholesterol": "CHOL", "cho": "CHOL", "chol": "CHOL",
    "hdl": "HDL", "ldl": "LDL",
    "sodium": "Na", "na": "Na",
    "potassium": "K", "k": "K",
    "chloride": "Cl", "cl": "Cl",
    "calcium": "Ca", "ca": "Ca",
    "magnesium": "Mg", "mg": "Mg",
    "phosphorus": "P", "p": "P",
    "tsh": "TSH", "crp": "CRP",
    "mcv": "MCV", "mch": "MCH", "mchc": "MCHC", "rdw": "RDW",
    "rdw-cv": "RDW-CV", "rdw-sd": "RDW-SD",
    "ck": "CK", "ldh": "LDH",
    "egfr": "eGFR", "gfr": "eGFR",
    # 白细胞分类
    "neut%": "NEUT%", "neut#": "NEUT#",
    "neu%": "NEUT%", "neu#": "NEUT#",
    "lymph%": "LYMPH%", "lymph#": "LYMPH#",
    "lym%": "LYMPH%", "lym#": "LYMPH#",
    "mono%": "MONO%", "mono#": "MONO#",
    "mon%": "MONO%", "mon#": "MONO#",
    "eo%": "EO%", "eo#": "EO#",
    "eos%": "EO%", "eos#": "EO#",
    "baso%": "BASO%", "baso#": "BASO#",
    "bas%": "BASO%", "bas#": "BASO#",
    # 血小板参数
    "mpv": "MPV", "pct": "PCT", "pdw": "PDW", "p-lcr": "P-LCR", "p-lcc": "P-LCC",

    # 中文名称
    "血肌酐": "Cr", "肌酐": "Cr",
    "尿素氮": "BUN", "尿素": "BUN",
    "尿酸": "UA", "血糖": "GLU", "葡萄糖": "GLU",
    "血红蛋白": "HB", "白细胞": "WBC", "白细胞计数": "WBC",
    "红细胞": "RBC", "红细胞计数": "RBC",
    "血小板": "PLT", "血小板计数": "PLT",
    "丙氨酸氨基转移酶": "ALT", "谷丙转氨酶": "ALT",
    "天冬氨酸氨基转移酶": "AST", "谷草转氨酶": "AST",
    "总胆红素": "TBIL", "直接胆红素": "DBIL",
    "总蛋白": "TP", "白蛋白": "ALB",
    "甘油三酯": "TG", "总胆固醇": "CHOL",
    "高密度脂蛋白": "HDL", "低密度脂蛋白": "LDL",
    "钠": "Na", "钾": "K", "氯": "Cl",
    "钙": "Ca", "镁": "Mg", "磷": "P",
    "促甲状腺激素": "TSH", "C反应蛋白": "CRP",
    "碱性磷酸酶": "ALP", "γ-谷氨酰转移酶": "GGT",
    # 白细胞分类中文
    "中性粒细胞百分比": "NEUT%", "中性粒细胞数": "NEUT#",
    "淋巴细胞百分比": "LYMPH%", "淋巴细胞数": "LYMPH#",
    "单核细胞百分比": "MONO%", "单核细胞数": "MONO#",
    "嗜酸性粒细胞百分比": "EO%", "嗜酸性粒细胞数": "EO#",
    "嗜碱性粒细胞百分比": "BASO%", "嗜碱性粒细胞数": "BASO#",
    # 血小板参数中文
    "平均血小板体积": "MPV", "血小板压积": "PCT",
    "血小板分布宽度": "PDW", "大血小板比率": "P-LCR",
    # 红细胞参数中文
    "红细胞分布宽度": "RDW", "红细胞分布宽度-cv": "RDW-CV",
    "红细胞分布宽度-sd": "RDW-SD",
}


def _resolve_key(ocr_key: str) -> str:
    """将 OCR 返回的 key 转换为参考范围数据库的 key"""
    n = ocr_key.strip().lower().replace(" ", "").replace("（", "(").replace("）", ")")
    return _KEY_ALIAS.get(n, ocr_key.upper())


# ═══════════════════════════════════════════════════════════════
# 年龄分层
# ═══════════════════════════════════════════════════════════════

def _get_age_group(age: int) -> str:
    """根据年龄返回年龄分层"""
    if age <= 0:
        return "adult"  # 默认
    elif age < 1:
        return "infant"
    elif age < 12:
        return "child"
    elif age < 18:
        return "adolescent"
    elif age < 65:
        return "adult"
    else:
        return "elderly"


def _get_gender_key(gender: str) -> str:
    """标准化性别键"""
    g = gender.strip().lower()
    if g in ("男", "male", "m"):
        return "male"
    elif g in ("女", "female", "f"):
        return "female"
    return ""


# ═══════════════════════════════════════════════════════════════
# 指标别名映射（中文/英文 → 标准 key）
# ═══════════════════════════════════════════════════════════════

_INDICATOR_ALIASES = {
    "cr": "creatinine", "crea": "creatinine", "creat": "creatinine",
    "bun": "bun", "urea": "bun",
    "ua": "uric_acid", "la": "uric_acid", "glu": "glucose",
    "hb": "hemoglobin", "hgb": "hemoglobin", "hct": "hematocrit",
    "wbc": "wbc", "rbc": "rbc", "plt": "plt",
    "alt": "alt", "ast": "ast", "ggt": "ggt", "alp": "alp",
    "tbil": "tbil", "dbil": "dbil", "tp": "total_protein",
    "alb": "albumin", "tg": "triglyceride", "cho": "cholesterol",
    "chol": "cholesterol", "ldl": "ldl", "hdl": "hdl",
    "na": "sodium", "k": "potassium", "cl": "chloride",
    "ca": "calcium", "mg": "magnesium", "p": "phosphorus",
    "tsh": "tsh", "crp": "crp",
    "mcv": "mcv", "mch": "mch", "mchc": "mchc", "rdw": "rdw",
    "rdw-cv": "rdw-cv", "rdw-sd": "rdw-sd",
    "ck": "ck", "ldh": "ldh",
    "egfr": "egfr", "gfr": "egfr",
    # 白细胞分类
    "neut%": "neut%", "neut#": "neut#",
    "neu%": "neut%", "neu#": "neut#",
    "lymph%": "lymph%", "lymph#": "lymph#",
    "lym%": "lymph%", "lym#": "lymph#",
    "mono%": "mono%", "mono#": "mono#",
    "mon%": "mono%", "mon#": "mono#",
    "eo%": "eo%", "eo#": "eo#",
    "eos%": "eo%", "eos#": "eo#",
    "baso%": "baso%", "baso#": "baso#",
    "bas%": "baso%", "bas#": "baso#",
    # 血小板参数
    "mpv": "mpv", "pct": "pct", "pdw": "pdw", "p-lcr": "p-lcr",
    # 中文名称
    "血肌酐": "creatinine", "肌酐": "creatinine",
    "尿素氮": "bun", "尿素": "bun",
    "尿酸": "uric_acid", "血糖": "glucose", "葡萄糖": "glucose",
    "血红蛋白": "hemoglobin", "白细胞": "wbc", "白细胞计数": "wbc",
    "红细胞": "rbc", "红细胞计数": "rbc",
    "血小板": "plt", "血小板计数": "plt",
    "丙氨酸氨基转移酶": "alt", "谷丙转氨酶": "alt",
    "天冬氨酸氨基转移酶": "ast", "谷草转氨酶": "ast",
    "总胆红素": "tbil", "直接胆红素": "dbil",
    "总蛋白": "total_protein", "白蛋白": "albumin",
    "甘油三酯": "triglyceride", "总胆固醇": "cholesterol",
    "高密度脂蛋白": "hdl", "低密度脂蛋白": "ldl",
    "钠": "sodium", "钾": "potassium", "氯": "chloride",
    "钙": "calcium", "镁": "magnesium", "磷": "phosphorus",
    "促甲状腺激素": "tsh", "C反应蛋白": "crp",
    "碱性磷酸酶": "alp", "γ-谷氨酰转移酶": "ggt",
    # 白细胞分类中文
    "中性粒细胞百分比": "neut%", "中性粒细胞数": "neut#",
    "淋巴细胞百分比": "lymph%", "淋巴细胞数": "lymph#",
    "单核细胞百分比": "mono%", "单核细胞数": "mono#",
    "嗜酸性粒细胞百分比": "eo%", "嗜酸性粒细胞数": "eo#",
    "嗜碱性粒细胞百分比": "baso%", "嗜碱性粒细胞数": "baso#",
    # 血小板参数中文
    "平均血小板体积": "mpv", "血小板压积": "pct",
    "血小板分布宽度": "pdw", "大血小板比率": "p-lcr",
    # 红细胞参数中文
    "红细胞分布宽度": "rdw", "红细胞分布宽度-cv": "rdw-cv",
    "红细胞分布宽度-sd": "rdw-sd",
}


def _normalize_key(name: str) -> str:
    n = name.strip().lower().replace(" ", "").replace("（", "(").replace("）", ")")
    return _INDICATOR_ALIASES.get(n, n)


def _extract_number(text: str) -> Optional[float]:
    if not text:
        return None
    text = text.replace("＞", ">").replace("＜", "<")
    m = re.search(r'(\d+\.?\d*)', text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


# ═══════════════════════════════════════════════════════════════
# Markdown 解析：原始文本 → patient_labs 字典
# ═══════════════════════════════════════════════════════════════

def parse_markdown_to_patient_labs(markdown_text: str) -> dict[str, float]:
    """
    解析 MinerU 输出的原始 Markdown，提取指标字典

    Args:
        markdown_text: MinerU full.md 原始文本

    Returns:
        {"wbc": 6.7, "hemoglobin": 106.0, ...}
    """
    parsed = []

    # 策略 A: HTML 表格（MinerU vlm/pipeline 输出格式）
    if "<table>" in markdown_text:
        parsed = _parse_html_table(markdown_text)

    # 策略 B: Markdown 表格
    if not parsed:
        lines = markdown_text.strip().split("\n")
        table_lines = [l for l in lines if l.strip().startswith("|") and l.strip().endswith("|")]
        if len(table_lines) >= 2:
            parsed = _parse_markdown_table(table_lines)

    # 策略 C: 正则逐行解析
    if not parsed:
        parsed = _parse_text_lines(markdown_text.strip().split("\n"))

    # 构建 patient_labs 字典
    patient_labs = {}
    for ind in parsed:
        key = ind.get("key", "")
        value = ind.get("value")
        if key and value is not None:
            patient_labs[key] = value

    logger.info("Markdown 解析完成: %d 个指标", len(patient_labs))
    return patient_labs


def _parse_html_table(html_text: str) -> list[dict]:
    parsed = []
    rows = re.findall(r'<tr>(.*?)</tr>', html_text, re.DOTALL)
    if len(rows) < 2:
        return []

    header_cells = re.findall(r'<td>(.*?)</td>', rows[0], re.DOTALL)
    header_cells = [h.strip().lower() for h in header_cells]

    col_map = {}
    for i, h in enumerate(header_cells):
        if any(kw in h for kw in ["项目", "名称", "检验", "指标", "item", "test", "name", "参数"]):
            col_map["name"] = i
        elif any(kw in h for kw in ["结果", "数值", "测定", "result", "value"]):
            col_map["value"] = i
        elif any(kw in h for kw in ["单位", "unit"]):
            col_map["unit"] = i
        elif any(kw in h for kw in ["参考", "范围", "区间", "ref", "range", "normal"]):
            col_map["ref_range"] = i
        elif any(kw in h for kw in ["缩写", "英文", "abbr", "code"]):
            col_map["eng"] = i

    if "name" not in col_map and len(header_cells) >= 1:
        col_map["name"] = 0
    if "value" not in col_map and len(header_cells) >= 2:
        col_map["value"] = 1

    for row in rows[1:]:
        cells = re.findall(r'<td>(.*?)</td>', row, re.DOTALL)
        cells = [c.strip() for c in cells]
        if not cells:
            continue

        name = cells[col_map["name"]] if "name" in col_map and col_map["name"] < len(cells) else ""
        eng = cells[col_map["eng"]] if "eng" in col_map and col_map["eng"] < len(cells) else ""
        value_raw = cells[col_map["value"]] if "value" in col_map and col_map["value"] < len(cells) else ""
        value = _extract_number(value_raw)
        unit = cells[col_map["unit"]] if "unit" in col_map and col_map["unit"] < len(cells) else ""
        ref_range = cells[col_map["ref_range"]] if "ref_range" in col_map and col_map["ref_range"] < len(cells) else ""

        # 跳过序号列（纯数字的 name）
        if name and name.isdigit():
            # 如果 name 是纯数字，可能是序号，尝试使用下一列作为 name
            name_idx = col_map.get("name", 0)
            if name_idx + 1 < len(cells):
                name = cells[name_idx + 1]
                # 重新提取 value
                if name_idx + 2 < len(cells):
                    value_raw = cells[name_idx + 2]
                    value = _extract_number(value_raw)
                if name_idx + 3 < len(cells):
                    unit = cells[name_idx + 3]
                if name_idx + 4 < len(cells):
                    ref_range = cells[name_idx + 4]

        if not name or value is None:
            continue

        key = _normalize_key(eng or name)
        parsed.append({"name": name, "eng": eng.lower() if eng else "", "key": key, "value": value, "unit": unit, "ref_range": ref_range})

    return parsed


def _parse_markdown_table(table_lines: list[str]) -> list[dict]:
    if len(table_lines) < 2:
        return []

    header_line = table_lines[0]
    headers = [h.strip().lower() for h in header_line.strip("|").split("|")]

    col_map = {}
    for i, h in enumerate(headers):
        h_clean = h.strip()
        if any(kw in h_clean for kw in ["项目", "名称", "检验", "指标", "item", "test", "name"]):
            col_map["name"] = i
        elif any(kw in h_clean for kw in ["结果", "数值", "测定", "result", "value"]):
            col_map["value"] = i
        elif any(kw in h_clean for kw in ["单位", "unit"]):
            col_map["unit"] = i
        elif any(kw in h_clean for kw in ["参考", "范围", "区间", "ref", "range", "normal"]):
            col_map["ref_range"] = i
        elif any(kw in h_clean for kw in ["缩写", "英文", "abbr", "code"]):
            col_map["eng"] = i

    if "name" not in col_map and len(headers) >= 1:
        col_map["name"] = 0
    if "value" not in col_map and len(headers) >= 2:
        col_map["value"] = 1

    parsed = []
    for line in table_lines[2:]:
        line = line.strip()
        if not line or line.startswith("|---") or line.startswith("|--"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]

        name = cells[col_map["name"]] if "name" in col_map and col_map["name"] < len(cells) else ""
        eng = cells[col_map["eng"]] if "eng" in col_map and col_map["eng"] < len(cells) else ""
        value_raw = cells[col_map["value"]] if "value" in col_map and col_map["value"] < len(cells) else ""
        value = _extract_number(value_raw)
        unit = cells[col_map["unit"]] if "unit" in col_map and col_map["unit"] < len(cells) else ""
        ref_range = cells[col_map["ref_range"]] if "ref_range" in col_map and col_map["ref_range"] < len(cells) else ""

        if not name or value is None:
            continue

        key = _normalize_key(eng or name)
        parsed.append({"name": name, "eng": eng.lower() if eng else "", "key": key, "value": value, "unit": unit, "ref_range": ref_range})

    return parsed


def _parse_text_lines(lines: list[str]) -> list[dict]:
    parsed = []
    known_keywords = [
        ("creatinine", "肌酐"), ("urea", "尿素"), ("bun", "尿素氮"),
        ("uric_acid", "尿酸"), ("glucose", "血糖"), ("glu", "葡萄糖"),
        ("hemoglobin", "血红蛋白"), ("wbc", "白细胞"), ("rbc", "红细胞"),
        ("plt", "血小板"), ("alt", "丙氨酸"), ("ast", "天冬"),
        ("tbil", "胆红素"), ("albumin", "白蛋白"), ("cholesterol", "胆固醇"),
        ("triglyceride", "甘油三酯"), ("sodium", "钠"), ("potassium", "钾"),
        ("calcium", "钙"), ("tsh", "促甲状腺"), ("crp", "C反应蛋白"),
        ("total_protein", "总蛋白"), ("ggt", "谷氨酰"), ("alp", "碱性磷酸酶"),
        ("hdl", "高密度"), ("ldl", "低密度"), ("hematocrit", "红细胞比容"),
    ]

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        lower = line.lower().replace(" ", "").replace("（", "(").replace("）", ")")
        has_keyword = any(alias in lower or chinese in line for alias, chinese in known_keywords)
        if not has_keyword:
            continue
        ind = _regex_parse_one_line(line)
        if ind:
            parsed.append(ind)
    return parsed


def _regex_parse_one_line(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None

    raw_name, eng = "", ""
    m1 = re.match(r'^(.+?)\s*[（(]\s*([A-Za-z]+[A-Za-z0-9#%/]*)\s*[）)]', text)
    if m1:
        raw_name, eng = m1.group(1).strip(), m1.group(2).strip().lower()
    if not raw_name:
        m2 = re.match(r'^(.+?)\s*[:：]', text)
        if m2:
            raw_name = m2.group(1).strip()
    if not raw_name:
        m3 = re.match(r'^(.+?)\s+(?=[\d<>.↑↓])', text)
        if m3:
            raw_name = m3.group(1).strip()

    value = None
    for p in [r'(\d+\.?\d*)\s*[×xX\*]\s*10[⁰¹²³⁴⁵⁶⁷⁸⁹]?\s*/?\s*[Ll]?', r'(\d+\.?\d*)\s*[a-zA-Zμ×/]', r'(\d+\.?\d*)']:
        vm = re.search(p, text)
        if vm:
            try:
                value = float(vm.group(1))
            except ValueError:
                continue
            break
    if value is None:
        return None

    unit = ""
    um = re.search(r'(?:μmol/L|mmol/L|×10[⁰¹²³⁴⁵⁶⁷⁸⁹]?/L|g/L|g/dL|mg/dL|U/L|mIU/L|nmol/L|pg/mL|fL|pg|%|mL/min|mm/h)', text, re.IGNORECASE)
    if um:
        unit = um.group()

    ref_range = ""
    for p in [r'(\d+\.?\d*\s*[-~<＞]\s*\d+\.?\d*)', r'([<＞]\s*\d+\.?\d*)']:
        rm = re.search(p, text)
        if rm:
            ref_range = rm.group(1)
            break

    key = _normalize_key(eng or raw_name)
    return {"name": raw_name or eng or text[:20], "eng": eng, "key": key, "value": value, "unit": unit, "ref_range": ref_range}


# ═══════════════════════════════════════════════════════════════
# 核心分析函数
# ═══════════════════════════════════════════════════════════════

def analyze_indicators(
    patient_labs: dict[str, float],
    age: int = 0,
    gender: str = "",
) -> list[dict]:
    """
    分析所有指标，判断状态

    Args:
        patient_labs: {ocr_key: value} 字典，如 {"wbc": 5.60, "hemoglobin": 154.0}
        age: 患者年龄
        gender: 患者性别 ("男"/"女"/"male"/"female")

    Returns:
        [
            {
                "key": "wbc",
                "name": "白细胞计数",
                "value": 5.60,
                "unit": "×10⁹/L",
                "ref_range": "4.5~11.0",
                "status": "normal"  # normal / high / low / critical_high / critical_low
            },
            ...
        ]
    """
    results = []

    for ocr_key, value in patient_labs.items():
        indicator = _analyze_one_indicator(ocr_key, value, age, gender)
        if indicator:
            results.append(indicator)

    # 按 key 排序
    results.sort(key=lambda x: x["key"])

    logger.info("分析完成: %d 个指标 (%d 正常, %d 异常)",
                len(results),
                sum(1 for r in results if r["status"] == "normal"),
                sum(1 for r in results if r["status"] != "normal"))

    return results


def _analyze_one_indicator(
    ocr_key: str,
    value: float,
    age: int,
    gender: str,
) -> Optional[dict]:
    """分析单个指标"""
    # 转换 key
    ref_key = _resolve_key(ocr_key)

    # 获取参考范围
    ref_info = REFERENCE_RANGES.get(ref_key)
    if not ref_info:
        # 没有参考范围信息，返回基本信息
        return {
            "key": ocr_key,
            "name": ocr_key,
            "value": value,
            "unit": "",
            "ref_range": "",
            "status": "normal",  # 无法判断，默认正常
        }

    # 提取中文名称
    name = ref_info.get("name", ocr_key)
    # 清理名称，去掉英文括号部分
    if "(" in name:
        name = name.split("(")[0].strip()

    unit = ref_info.get("unit", "")

    # 获取合适的参考范围
    age_group = _get_age_group(age)
    gender_key = _get_gender_key(gender)

    # 优先使用性别特定范围，其次使用年龄分层
    ref_range = None
    if gender_key and gender_key in ref_info:
        ref_range = ref_info[gender_key]
    elif age_group in ref_info:
        ref_range = ref_info[age_group]
    elif "normal" in ref_info:
        ref_range = ref_info["normal"]
    elif "adult" in ref_info:
        ref_range = ref_info["adult"]

    # 判断状态
    status = "normal"
    if ref_range:
        min_val = ref_range.get("min")
        max_val = ref_range.get("max")

        # 检查危急值
        critical_high = ref_info.get("critical_high")
        critical_low = ref_info.get("critical_low")

        if critical_high is not None and value >= critical_high:
            status = "critical_high"
        elif critical_low is not None and value <= critical_low:
            status = "critical_low"
        elif max_val is not None and value > max_val:
            status = "high"
        elif min_val is not None and value < min_val:
            status = "low"
        else:
            status = "normal"

    # 构建参考范围文本
    ref_range_text = ""
    if ref_range:
        min_val = ref_range.get("min")
        max_val = ref_range.get("max")
        if min_val is not None and max_val is not None:
            ref_range_text = f"{min_val}~{max_val}"
        elif min_val is not None:
            ref_range_text = f">{min_val}"
        elif max_val is not None:
            ref_range_text = f"<{max_val}"

    return {
        "key": ocr_key,
        "name": name,
        "value": value,
        "unit": unit,
        "ref_range": ref_range_text,
        "status": status,
    }


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def get_abnormal_indicators(indicators: list[dict]) -> list[dict]:
    """获取所有异常指标"""
    return [ind for ind in indicators if ind["status"] != "normal"]


def get_critical_indicators(indicators: list[dict]) -> list[dict]:
    """获取所有危急值指标"""
    return [ind for ind in indicators if ind["status"].startswith("critical")]


def format_indicator_text(indicator: dict) -> str:
    """格式化单个指标为可读文本"""
    status_map = {
        "normal": "✅ 正常",
        "high": "⬆️ 偏高",
        "low": "⬇️ 偏低",
        "critical_high": "🚨 危急偏高",
        "critical_low": "🚨 危急偏低",
    }
    status_text = status_map.get(indicator["status"], indicator["status"])

    parts = [
        f"{indicator['name']}（{indicator['key']}）",
        f"值: {indicator['value']} {indicator['unit']}",
    ]
    if indicator["ref_range"]:
        parts.append(f"参考: {indicator['ref_range']}")
    parts.append(f"状态: {status_text}")

    return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 测试数据
    test_labs = {
        "wbc": 5.60,
        "rbc": 4.82,
        "hemoglobin": 154.0,
        "plt": 246,
        "creatinine": 96.2,
        "uric_acid": 308,
    }

    print("测试数据:", test_labs)
    print()

    indicators = analyze_indicators(test_labs, age=31, gender="male")

    print("分析结果:")
    for ind in indicators:
        print(f"  {format_indicator_text(ind)}")

    print()
    print(f"总计: {len(indicators)} 项")
    print(f"正常: {sum(1 for i in indicators if i['status'] == 'normal')} 项")
    print(f"异常: {sum(1 for i in indicators if i['status'] != 'normal')} 项")
