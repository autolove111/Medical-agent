"""
PaddleOCR 化验单识别引擎 (v2.8.1)

双层架构：
  Layer 1 — 通用文本提取：PaddleOCR 识别所有文字，永远输出完整原始文本
  Layer 2 — 多策略解析：表格解析 → 逐行正则 → 兜底（解析失败不丢数据）
"""

from __future__ import annotations

import logging
import re
import os
from typing import Optional

logger = logging.getLogger("paddle_ocr")

# ── 别名映射表 ────────────────────────────────────────────
_KEY_ALIAS: dict[str, str] = {
    "cr": "creatinine", "crea": "creatinine", "creat": "creatinine",
    "bun": "bun", "urea": "bun",
    "ua": "uric_acid", "uric": "uric_acid", "la": "uric_acid", "glu": "glucose",
    "hb": "hemoglobin", "hgb": "hemoglobin", "hct": "hematocrit",
    "wbc": "wbc", "rbc": "rbc", "plt": "plt",
    "alt": "alt", "ast": "ast", "ggt": "ggt", "alp": "alp",
    "ggty": "ggt",
    "tbil": "tbil", "dbil": "dbil", "tp": "total_protein",
    "alb": "albumin", "tg": "triglyceride", "cho": "cholesterol",
    "chol": "cholesterol", "ldl": "ldl", "hdl": "hdl",
    "na": "sodium", "k": "potassium", "cl": "chloride",
    "ca": "calcium", "mg": "magnesium", "p": "phosphorus",
    "phos": "phosphorus", "po4": "phosphorus",
    "tsh": "tsh", "t3": "t3", "t4": "t4", "crp": "crp",
    "hcrp": "crp",
    "mcv": "mcv", "mch": "mch", "mchc": "mchc", "rdw": "rdw",
    "ne": "ne", "ly": "ly", "mo": "mo", "eo": "eo", "ba": "ba",
    "ck": "ck", "ldh": "ldh", "bnp": "bnp",
    "ckmb": "ck_mb", "ck-mb": "ck_mb",
    "egfr": "egfr", "gfr": "egfr",
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
    "碱性磷酸酶": "alp", "γ-谷氨酰转肽酶": "ggt",
}


def _normalize_key(name: str) -> str:
    n = name.strip().lower().replace(" ", "").replace("（", "(").replace("）", ")")
    n = re.sub(r"^[\d*★#\s]+", "", n)
    if n in _KEY_ALIAS:
        return _KEY_ALIAS[n]
    code_match = re.match(r"([a-z][a-z0-9/_-]*)", n)
    if code_match:
        code = code_match.group(1).rstrip("-_/")
        if code.startswith("co2"):
            return "co2"
        if code in _KEY_ALIAS:
            return _KEY_ALIAS[code]
    try:
        from app.business.indicator_classifier import _resolve_key
        r = _resolve_key(n)
        if r != n:
            return r
    except ImportError:
        pass
    return n


# ── 主类 ──────────────────────────────────────────────────

class PaddleLabOCR:
    """PaddleOCR 化验单识别器"""

    def __init__(self, use_gpu: bool = False):
        self._ocr = None
        self._use_gpu = use_gpu
        self._loaded = False

    def _lazy_load(self):
        if self._loaded:
            return
        logger.info("Loading PaddleOCR model...")
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(lang="ch", use_angle_cls=True,
                              use_gpu=self._use_gpu, show_log=False)
        self._loaded = True
        logger.info("PaddleOCR loaded (GPU=%s)", self._use_gpu)

    # ================================================================
    # 公开 API
    # ================================================================

    def recognize(self, image_path: str) -> dict:
        """
        识别化验单图片。

        返回格式（与旧 OCR 服务兼容）:
        {
            "raw_lines": ["尿素", "4.47", "mmol/L", ...],     ← 所有原始文本
            "full_extraction": ["尿素: 4.47 mmol/L", ...],     ← 人可读行
            "layout_type": "table",                             ← 检测到的布局类型
            "gat_structured": {
                "patient_labs": {"bun": 4.47, ...},            ← 结构化指标
                "mapped_count": 4, "total_items": 28,
                "coverage": "100%"
            }
        }
        """
        self._lazy_load()
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片不存在: {image_path}")

        # ── Layer 1: 通用文本提取 ──
        raw_items = self._extract_all_text(image_path)
        raw_lines = [it["text"] for it in raw_items]

        # ── Layer 2: 多策略解析 ──
        table_indicators = self._parse_table_layout(raw_items)

        merged_labs = {}
        full_extraction = []

        # 表格解析结果
        for ind in table_indicators:
            merged_labs[ind["key"]] = ind["value"]
            full_extraction.append(
                f"{ind['name']}: {ind['value']} {ind['unit']}".strip()
            )

        regex_indicators = []
        # 正则回退：仅当表格解析覆盖率低时启用
        if len(table_indicators) < 3:
            regex_indicators = self._parse_regex_lines(raw_lines)
            table_keys = {ind["key"] for ind in table_indicators}
            for ind in regex_indicators:
                if ind["key"] not in table_keys:
                    merged_labs[ind["key"]] = ind["value"]
                    full_extraction.append(
                        f"{ind['name']}: {ind['value']} {ind['unit']}".strip()
                    )

        # 如果两种解析都失败了，至少返回原始文本行
        if not full_extraction:
            full_extraction = raw_lines
            layout = "unknown"
        elif table_indicators:
            layout = "table"
        else:
            layout = "free_text"

        logger.info(
            "OCR: %d raw items → table=%d + regex=%d → merged=%d | layout=%s",
            len(raw_items), len(table_indicators), len(regex_indicators),
            len(merged_labs), layout,
        )

        return {
            "raw_lines": raw_lines,
            "full_extraction": full_extraction,
            "layout_type": layout,
            "gat_structured": {
                "patient_labs": merged_labs,
                "base_labs": merged_labs,
                "ratio_labs": {},
                "mapped_count": len(merged_labs),
                "total_items": len(raw_items),
                "coverage": f"{len(merged_labs) * 100 // max(1, len(raw_items))}%"
                    if raw_items else "0%",
            },
        }

    # ================================================================
    # Layer 1: 通用文本提取
    # ================================================================

    def _extract_all_text(self, image_path: str) -> list[dict]:
        """
        PaddleOCR 提取全部文本块（含坐标），按阅读顺序排列。

        返回: [{"text": "尿素", "y": 136, "x": 243, "w": width, "conf": 0.99}, ...]
        """
        results = self._ocr.ocr(image_path, cls=True)
        if not results or not results[0]:
            return []

        items = []
        for page in results:
            for item in page:
                if len(item) < 2:
                    continue
                bbox = item[0]
                info = item[1]
                if isinstance(info, (list, tuple)) and len(info) >= 2:
                    text, conf = str(info[0]).strip(), info[1]
                else:
                    text, conf = str(info), 1.0
                if conf < 0.4 or not text:
                    continue

                items.append({
                    "text": text,
                    "y": (bbox[0][1] + bbox[2][1]) / 2,
                    "x": bbox[0][0],
                    "w": abs(bbox[1][0] - bbox[0][0]),
                    "conf": conf,
                })

        # 按阅读顺序排列：从上到下，从左到右
        items.sort(key=lambda it: (it["y"], it["x"]))
        return items

    # ================================================================
    # Layer 2a: 表格布局解析
    # ================================================================

    def _parse_table_layout(self, items: list[dict]) -> list[dict]:
        """尝试表格布局解析，失败返回空列表"""
        if not items:
            return []

        # 检测表格特征：是否有明显的列对齐
        x_values = [it["x"] for it in items]
        x_spread = max(x_values) - min(x_values) if x_values else 0
        if x_spread < 400:
            # 文本宽度太窄，不是表格布局
            return []

        rows = self._group_by_y(items, tolerance=8)
        parsed = []
        for row_items in rows:
            row_items.sort(key=lambda it: it["x"])
            for segment in self._split_row_segments(row_items):
                ind = self._parse_table_row(segment)
                if ind:
                    parsed.append(ind)

        # 表格解析至少要有 2 个结果才认为有效
        if len(parsed) < 2:
            return []
        return parsed

    @staticmethod
    def _split_row_segments(items: list[dict]) -> list[list[dict]]:
        """
        常见检验单会把表格拆成左右两栏。PaddleOCR 按 y 合并后，
        同一行可能同时包含左右两栏的两个检验项，必须先按 x 拆开。
        """
        if len(items) < 6:
            return [items]

        x_min = min(it["x"] for it in items)
        x_max = max(it["x"] for it in items)
        if x_max - x_min < 650:
            return [items]

        midpoint = x_min + (x_max - x_min) / 2
        left = [it for it in items if it["x"] < midpoint]
        right = [it for it in items if it["x"] >= midpoint]
        segments = [seg for seg in (left, right) if len(seg) >= 2]
        return segments or [items]

    @staticmethod
    def _group_by_y(items: list[dict], tolerance: float = 45) -> list[list[dict]]:
        if not items:
            return []
        sorted_items = sorted(items, key=lambda it: it["y"])
        rows = [[sorted_items[0]]]
        current_y = sorted_items[0]["y"]
        for item in sorted_items[1:]:
            if abs(item["y"] - current_y) <= tolerance:
                rows[-1].append(item)
            else:
                rows.append([item])
                current_y = item["y"]
        return rows

    def _parse_table_row(self, items: list[dict]) -> Optional[dict]:
        """
        从一行文本块中提取: 中文名 / 英文缩写 / 数值 / 参考范围 / 单位
        硬编码 X 坐标阈值（适用于常见化验单列宽比例）
        """
        seq_result = self._parse_table_row_by_sequence(items)
        if seq_result:
            return seq_result

        # 动态计算列的 X 分界点（适用于不同缩放比例）
        x_values = sorted(it["x"] for it in items)
        if len(x_values) < 2:
            return None

        x_min = x_values[0]
        x_max = x_values[-1]
        span = x_max - x_min

        # 按比例划分列区间
        col_name = x_min + span * 0.25     # 名称列右边界
        col_value = x_min + span * 0.60    # 数值列右边界
        col_ref = x_min + span * 0.82      # 参考范围右边界

        eng = ""; name = ""; value = None; unit = ""; ref_range = ""

        for it in items:
            x, t = it["x"], it["text"]

            # 跳过纯序号
            if re.match(r'^\d{1,2}$', t):
                continue
            if any(header in t for header in ("序号", "检验项目", "结果", "提示", "单位", "参考区间")):
                continue

            if x < col_name:
                cleaned = re.sub(r"^\d+", "", t).strip()
                if re.search(r'[A-Za-z]', cleaned):
                    m = re.search(r'[A-Za-z][A-Za-z0-9/_-]*', cleaned)
                    if m:
                        eng = m.group(0)
                if re.search(r'[一-鿿A-Za-z]', cleaned) and len(cleaned) > len(name):
                    name = cleaned
            elif x < col_value:
                vm = re.search(r'(\d+\.?\d*)', t)
                if vm and value is None:
                    value = float(vm.group(1))
            elif x < col_ref:
                if not ref_range:
                    ref_range = t
            else:
                if not unit:
                    unit = t

        if not name and eng:
            name = eng
        if not name or value is None:
            return None

        key = _normalize_key(eng or name)
        return {
            "name": name, "eng": eng.lower() if eng else "",
            "key": key, "value": value,
            "unit": unit, "ref_range": ref_range,
        }

    def _parse_table_row_by_sequence(self, items: list[dict]) -> Optional[dict]:
        """
        按顺序解析常见检验单行：序号、项目名、结果、单位/参考范围。
        这比列宽比例更能适配 OCR 把“单位+参考范围”合成一个文本块的情况。
        """
        sorted_items = sorted(items, key=lambda it: it["x"])
        header_words = ("序号", "检验项目", "结果", "提示", "单位", "参考区间")

        name = ""
        name_index = -1
        eng = ""

        for idx, it in enumerate(sorted_items):
            text = it["text"].strip()
            if not text or any(word in text for word in header_words):
                continue
            if re.match(r"^\d{1,2}$", text):
                continue
            if re.match(r"^[A-Za-z]$", text):
                continue
            if not re.search(r"[A-Za-z一-鿿]", text):
                continue
            if re.match(r"^(?:mmol/L|umol/L|μmol/L|g/L|mg/L|U/L)", text, re.IGNORECASE):
                continue

            cleaned = re.sub(r"^\d+", "", text).strip()
            name = cleaned
            name_index = idx
            m = re.search(r"[A-Za-z][A-Za-z0-9/_-]*", cleaned)
            if m:
                eng = m.group(0)
            break

        if not name or name_index < 0:
            return None

        value = None
        value_index = -1
        for idx, it in enumerate(sorted_items[name_index + 1:], start=name_index + 1):
            text = it["text"]
            vm = re.search(r"[-+]?\d+\.?\d*", text)
            if vm:
                value = float(vm.group(0))
                value_index = idx
                break

        if value is None:
            return None

        trailing = " ".join(it["text"] for it in sorted_items[value_index + 1:])
        unit = ""
        um = re.search(
            r"(?:μmol/L|umol/L|mmol/L|×10[⁹¹²]/L|g/L|g/dL|mg/L|mg/dL|U/L|mIU/L|nmol/L|pg/mL|fL|pg|%|mL/min)",
            trailing,
            re.IGNORECASE,
        )
        if um:
            unit = um.group(0)

        ref_range = ""
        rm = re.search(r"(\d+\.?\d*\s*[-~]\s*\d+\.?\d*|[<＞>]\s*\d+\.?\d*)", trailing)
        if rm:
            ref_range = rm.group(1)

        key = _normalize_key(eng or name)
        if not key:
            return None
        return {
            "name": name, "eng": eng.lower() if eng else "",
            "key": key, "value": value,
            "unit": unit, "ref_range": ref_range,
        }

    # ================================================================
    # Layer 2b: 逐行正则解析（适用于非表格布局）
    # ================================================================

    def _parse_regex_lines(self, lines: list[str]) -> list[dict]:
        """
        逐行正则解析（仅用于非表格场景）。
        只解析包含已知指标名/缩写且含数值的行。
        """
        parsed = []
        for line in lines:
            # 预筛选：必须包含已知指标关键词或缩写
            lower = line.lower().replace(" ", "").replace("（", "(").replace("）", ")")
            has_known_keyword = any(
                alias in lower or chinese in line
                for alias, chinese in [
                    ("creatinine", "肌酐"), ("urea", "尿素"), ("bun", "尿素氮"),
                    ("uric_acid", "尿酸"), ("glucose", "血糖"), ("glu", "葡萄糖"),
                    ("hemoglobin", "血红蛋白"), ("wbc", "白细胞"), ("rbc", "红细胞"),
                    ("plt", "血小板"), ("alt", "丙氨酸"), ("ast", "天冬"),
                    ("tbil", "胆红素"), ("albumin", "白蛋白"), ("cholesterol", "胆固醇"),
                    ("triglyceride", "甘油三酯"), ("sodium", "钠"), ("potassium", "钾"),
                    ("calcium", "钙"), ("tsh", "促甲状腺"), ("crp", "C反应蛋白"),
                ]
            )
            if not has_known_keyword:
                continue

            ind = self._regex_parse_one(line)
            if ind:
                parsed.append(ind)
        return parsed

    def _regex_parse_one(self, text: str) -> Optional[dict]:
        """正则解析单行"""
        text = text.strip()
        if not text:
            return None

        flag = ""
        fm = re.search(r'[↑↓]', text)
        if fm:
            flag = fm.group()

        # 提取指标名
        raw_name = ""
        for pat in [r'^(.+?)\s*[：:]\s*', r'^(.+?)\s+(?=[\d<>.])']:
            m = re.match(pat, text)
            if m:
                raw_name = m.group(1).strip()
                break

        # 英文缩写（括号内）
        eng = ""
        em = re.search(r'\(([A-Za-z]+[A-Za-z0-9#%/]*)\)', raw_name)
        if em:
            eng = em.group(1).lower()
        clean_name = re.sub(r'\([^)]*\)', '', raw_name).strip()

        # 数值
        value = None
        for p in [r'(\d+\.?\d*)\s*[a-zA-Zμ×/]', r'(\d+\.?\d*)']:
            vm = re.search(p, text)
            if vm:
                value = float(vm.group(1))
                break
        if value is None:
            return None

        # 单位
        unit = ""
        um = re.search(
            r'(?:μmol/L|mmol/L|×10[⁹¹²]/L|g/L|g/dL|mg/dL|U/L|mIU/L|nmol/L|pg/mL|fL|pg|%|mL/min)',
            text, re.IGNORECASE,
        )
        if um:
            unit = um.group()

        # 参考范围
        ref_range = ""
        for p in [r'(\d+\.?\d*\s*[-~<＞>]\s*\d+\.?\d*)', r'([<＞>]\s*\d+\.?\d*)']:
            rm = re.search(p, text)
            if rm:
                ref_range = rm.group(1)
                break

        key = _normalize_key(eng or clean_name)
        return {
            "name": clean_name or eng or text[:20],
            "eng": eng, "key": key, "value": value,
            "unit": unit, "ref_range": ref_range, "flag": flag,
        }


# ── 单例 ──────────────────────────────────────────────────

_instance: Optional[PaddleLabOCR] = None


def get_paddle_ocr(use_gpu: bool = False) -> PaddleLabOCR:
    global _instance
    if _instance is None:
        _instance = PaddleLabOCR(use_gpu=use_gpu)
    return _instance
