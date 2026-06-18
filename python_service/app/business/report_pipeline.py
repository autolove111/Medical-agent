"""
报告处理管线：串联 OCR → 结构化提取 → 指标分类 → 联动分析 → 解读上下文生成

这是模块一（报告录入）和模块二（智能解读）之间的桥梁层。
上传报告后，通过此管线完成从原始 OCR 文本到可注入 Agent 的结构化上下文的完整流程。

OCR 引擎支持：
  - mineru_api:    MinerU 官方云 API（异步提交 → 轮询 → ZIP 下载 → full.md 解析）
  - mineru_docker: MinerU 本地 Docker 服务
  - mock:          内置演示数据
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.business.lab_report import LabReport, LabIndicator
from app.business.indicator_classifier import batch_classify
from app.business.correlation_engine import CorrelationEngine
from core.config import settings

logger = logging.getLogger(__name__)

# ── 路径常量 ─────────────────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
REPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


# ═══════════════════════════════════════════════════════════
# ReportPipeline
# ═══════════════════════════════════════════════════════════

class ReportPipeline:
    """报告处理管线"""

    def __init__(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(REPORT_DIR, exist_ok=True)
        self._correlation = CorrelationEngine()

    # ── OCR 入口 ──────────────────────────────────────────

    async def call_ocr(self, file_path: str) -> dict:
        """
        调用 OCR 引擎，返回结构化结果。

        路由逻辑：
          - OCR_ENGINE=mineru_api   → MinerU 官方云 API
          - OCR_ENGINE=mineru_docker → MinerU 本地 Docker
          - 其他 / 失败               → Mock 数据
        """
        engine = settings.OCR_ENGINE

        if engine in ("mineru_api", "mineru_docker"):
            try:
                return await self._call_mineru(file_path)
            except Exception as e:
                logger.warning("MinerU failed (%s), falling back to mock", e)
                return self._mock_ocr()

        # 兼容旧 OCR 服务（降级路径）
        ocr_url = f"{settings.OCR_SERVICE_URL}/api/v1/analyze-vision"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(ocr_url, json={"path": file_path, "force_recheck": False})
                resp.raise_for_status()
                result = resp.json()
                if "error" in result and result["error"]:
                    logger.warning("OCR service returned error: %s", result["error"])
                    return self._mock_ocr()
                logger.info("OCR success via legacy service: %d indicators",
                            result.get("gat_structured", {}).get("mapped_count", 0))
                return result
        except Exception as e:
            logger.warning("Legacy OCR unavailable (%s), using mock", e)
            return self._mock_ocr()

    # ── MinerU 主流程 ─────────────────────────────────────

    async def _call_mineru(self, file_path: str) -> dict:
        """
        MinerU 完整异步流程：

          1. POST /api/v4/file-urls/batch  提交任务 → 获得 task_id
          2. 轮询 GET /api/v4/extract/task/{task_id}  直到 state="done"
          3. 下载 full_zip_url → 解压 → 读取 full.md
          4. 解析 full.md 文本 → 构建 gat_structured 返回
        """
        logger.info("[MinerU] Starting extraction for: %s", file_path)

        # Step 1: 提交任务
        task_id = await self._mineru_submit(file_path)
        logger.info("[MinerU] Task submitted: %s", task_id)

        # Step 2: 轮询等待完成
        zip_url = await self._mineru_poll(task_id)
        logger.info("[MinerU] Task done, ZIP URL: %s", zip_url)

        # Step 3: 下载 ZIP → 解压 → 读 full.md
        markdown_text = await self._mineru_download_and_extract(zip_url)
        logger.info("[MinerU] Extracted full.md (%d chars)", len(markdown_text))

        # Step 4: 解析 Markdown → 构建结构化结果
        result = self._parse_markdown_to_structured(markdown_text)
        logger.info("[MinerU] Parsed %d indicators", result["gat_structured"]["mapped_count"])
        return result

    # ── Step 1: 提交任务 ──────────────────────────────────

    async def _mineru_submit(self, file_path: str) -> str:
        """Upload file to MinerU and create extraction task, return task_id.

        Two-step flow:
          1. POST /api/v4/file-urls/batch  upload file (base64) -> get OSS file_url
          2. POST /api/v4/extract/task     submit file_url -> get task_id
        """
        import base64 as b64_mod
        base_url = settings.MINERU_API_BASE_URL.rstrip("/")
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        headers = {}
        if settings.MINERU_API_TOKEN:
            headers["Authorization"] = f"Bearer {settings.MINERU_API_TOKEN}"

        with open(file_path, "rb") as f:
            file_content = f.read()

        b64_content = b64_mod.b64encode(file_content).decode("utf-8")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Upload file to MinerU OSS
            upload_url = f"{base_url}/api/v4/file-urls/batch"
            upload_payload = {
                "files": [{
                    "name": file_name,
                    "data": b64_content,
                    "size": file_size,
                }]
            }
            resp = await client.post(upload_url, headers=headers, json=upload_payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"MinerU upload failed: HTTP {resp.status_code} - {resp.text[:500]}"
                )
            upload_data = resp.json()
            if upload_data.get("code") != 0:
                raise RuntimeError(
                    f"MinerU upload error: {upload_data.get('msg', 'unknown')}"
                )

            file_urls = upload_data.get("data", {}).get("file_urls", [])
            if not file_urls:
                raise RuntimeError(
                    f"MinerU upload response missing file_urls: {upload_data}"
                )

            logger.info("[MinerU] File uploaded to OSS: %s", file_urls[0][:80])

            # Step 2: Create extraction task
            task_url = f"{base_url}/api/v4/extract/task"
            task_payload = {"url": file_urls[0]}
            resp2 = await client.post(task_url, headers=headers, json=task_payload)
            if resp2.status_code != 200:
                raise RuntimeError(
                    f"MinerU task creation failed: HTTP {resp2.status_code} - {resp2.text[:500]}"
                )
            task_data = resp2.json()
            if task_data.get("code") != 0:
                raise RuntimeError(
                    f"MinerU task creation error: {task_data.get('msg', 'unknown')}"
                )

            task_id = task_data.get("data", {}).get("task_id")
            if not task_id:
                raise RuntimeError(
                    f"MinerU task response missing task_id: {task_data}"
                )

            return task_id


    # ── Step 2: 轮询任务状态 ──────────────────────────────

    async def _mineru_poll(self, task_id: str) -> str:
        """轮询 MinerU 任务状态，返回 full_zip_url。"""
        base_url = settings.MINERU_API_BASE_URL.rstrip("/")
        poll_url = f"{base_url}/api/v4/extract/task/{task_id}"

        headers = {}
        if settings.MINERU_API_TOKEN:
            headers["Authorization"] = f"Bearer {settings.MINERU_API_TOKEN}"

        start_time = time.time()
        interval = settings.MINERU_POLL_INTERVAL
        timeout = settings.MINERU_POLL_TIMEOUT

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"MinerU task {task_id} timed out after {timeout}s")

                resp = await client.get(poll_url, headers=headers)
                if resp.status_code != 200:
                    # 可能还在处理中
                    logger.debug("Poll returned %d, retrying...", resp.status_code)
                    await asyncio.sleep(interval)
                    continue

                data = resp.json()
                state = data.get("state") or data.get("status") or ""

                if state == "done":
                    zip_url = data.get("full_zip_url") or data.get("data", {}).get("full_zip_url")
                    if not zip_url:
                        raise RuntimeError(f"MinerU task done but no full_zip_url in response: {data}")
                    return zip_url

                if state in ("failed", "error"):
                    err_msg = (
                        data.get("data", {}).get("err_msg")
                        or data.get("err_msg")
                        or data.get("error")
                        or data.get("message", "unknown error")
                    )
                    raise RuntimeError(f"MinerU task {task_id} failed: {err_msg}")

                # 仍然在处理中
                progress = data.get("progress", "")
                logger.debug("[MinerU] polling %s: state=%s progress=%s elapsed=%.0fs",
                              task_id, state, progress, elapsed)
                await asyncio.sleep(interval)

    # ── Step 3: 下载 ZIP → 解压 → 读取 full.md ─────────────

    async def _mineru_download_and_extract(self, zip_url: str) -> str:
        """下载 ZIP 压缩包，解压并返回 full.md 内容。"""
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.get(zip_url)
            resp.raise_for_status()

        zip_bytes = resp.content
        logger.info("[MinerU] Downloaded ZIP: %d bytes", len(zip_bytes))

        # 解压到临时目录
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # 找到解压后的根目录
            names = zf.namelist()
            # 常见的结构：解压后有一个顶层文件夹
            root_dirs = set()
            for name in names:
                parts = name.split("/")
                if parts[0]:
                    root_dirs.add(parts[0])

            # 解压到临时文件夹
            extract_dir = tempfile.mkdtemp(prefix="mineru_")
            zf.extractall(extract_dir)
            logger.info("[MinerU] Extracted to: %s (%d files)", extract_dir, len(names))

            # 查找 full.md
            full_md_path = None
            for root, dirs, files in os.walk(extract_dir):
                if "full.md" in files:
                    full_md_path = os.path.join(root, "full.md")
                    break

            if not full_md_path:
                # 列出所有文件帮助调试
                all_files = []
                for root, dirs, files in os.walk(extract_dir):
                    for f in files:
                        all_files.append(os.path.relpath(os.path.join(root, f), extract_dir))
                raise RuntimeError(
                    f"full.md not found in extracted ZIP. Available files: {all_files[:20]}"
                )

            with open(full_md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

            # 清理临时文件（可选，保留用于调试）
            # import shutil; shutil.rmtree(extract_dir, ignore_errors=True)

            return md_text

    # ── Step 4: 解析 Markdown → 结构化指标 ─────────────────

    def _parse_markdown_to_structured(self, markdown_text: str) -> dict:
        """
        解析 MinerU 的 full.md 输出，提取医学指标并构建 gat_structured 格式。

        MinerU 输出两种常见格式：
          A) Markdown 表格：  | 项目 | 结果 | 单位 | 参考范围 |
          B) 纯文本/列表：    每行一条 "指标名: 数值 单位"

        返回格式与原 OCR 服务兼容：
        {
            "cached": False,
            "analysis": [],
            "full_extraction": [...],
            "gat_structured": {
                "patient_labs": {key: value, ...},
                "base_labs": {},
                "ratio_labs": {},
                "mapped_count": N,
                "total_items": N,
                "coverage": "XX%",
            }
        }
        """
        lines = markdown_text.strip().split("\n")
        parsed_indicators = []

        # ── 策略 A: 检测 Markdown 表格 ──
        table_lines = [l for l in lines if l.strip().startswith("|") and l.strip().endswith("|")]
        if len(table_lines) >= 2:
            parsed_indicators = self._parse_markdown_table(table_lines)

        # ── 策略 B: 正则逐行解析 ──
        if not parsed_indicators:
            parsed_indicators = self._parse_text_lines(lines)

        # ── 构建 gat_structured ──
        patient_labs = {}
        for ind in parsed_indicators:
            key = ind.get("key", "")
            value = ind.get("value")
            if key and value is not None:
                patient_labs[key] = value

        mapped_count = len(patient_labs)
        total_items = len(parsed_indicators)
        coverage = f"{mapped_count * 100 // max(total_items, 1)}%"

        full_extraction = [
            f"{ind.get('name', '')}: {ind.get('value', '')} {ind.get('unit', '')}  [ref: {ind.get('ref_range', '')}]".strip()
            for ind in parsed_indicators
        ]

        return {
            "cached": False,
            "analysis": [],
            "full_extraction": full_extraction,
            "gat_structured": {
                "patient_labs": patient_labs,
                "base_labs": {},
                "ratio_labs": {},
                "mapped_count": mapped_count,
                "total_items": total_items,
                "coverage": coverage,
            },
        }

    def _parse_markdown_table(self, table_lines: list[str]) -> list[dict]:
        """解析 Markdown 表格，提取指标。"""
        # 找到表头行和分隔行
        if len(table_lines) < 2:
            return []

        header_line = table_lines[0]
        headers = [h.strip().lower() for h in header_line.strip("|").split("|")]

        # 识别列索引
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
            elif any(kw in h_clean for kw in ["缩写", "英文", "abbr", "code", "缩写名"]):
                col_map["eng"] = i

        # 如果没有找到 name/value 列，尝试前两列作为默认
        if "name" not in col_map and len(headers) >= 1:
            col_map["name"] = 0
        if "value" not in col_map and len(headers) >= 2:
            col_map["value"] = 1

        parsed = []
        for line in table_lines[2:]:  # 跳过表头和分隔行
            line = line.strip()
            if not line or line.startswith("|---") or line.startswith("|--"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]

            name = cells[col_map["name"]] if "name" in col_map and col_map["name"] < len(cells) else ""
            eng = cells[col_map["eng"]] if "eng" in col_map and col_map["eng"] < len(cells) else ""

            # 提取数值
            value_raw = cells[col_map["value"]] if "value" in col_map and col_map["value"] < len(cells) else ""
            value = self._extract_number(value_raw)

            unit = cells[col_map["unit"]] if "unit" in col_map and col_map["unit"] < len(cells) else ""
            ref_range = cells[col_map["ref_range"]] if "ref_range" in col_map and col_map["ref_range"] < len(cells) else ""

            if not name or value is None:
                continue

            key = self._normalize_indicator_key(eng or name)
            parsed.append({
                "name": name,
                "eng": eng.lower() if eng else "",
                "key": key,
                "value": value,
                "unit": unit,
                "ref_range": ref_range,
            })

        return parsed

    def _parse_text_lines(self, lines: list[str]) -> list[dict]:
        """正则逐行解析非表格文本中的指标。复用 paddle_ocr 的解析逻辑。"""
        parsed = []

        # 已知指标关键词
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
            ("mcv", "平均红细胞体积"), ("mch", "平均红细胞血红蛋白"),
            ("egfr", "肾小球滤过"), ("ck", "肌酸激酶"), ("ldh", "乳酸脱氢酶"),
            ("chloride", "氯"), ("magnesium", "镁"), ("phosphorus", "磷"),
        ]

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            lower = line.lower().replace(" ", "").replace("（", "(").replace("）", ")")
            has_keyword = any(
                alias in lower or chinese in line
                for alias, chinese in known_keywords
            )
            if not has_keyword:
                continue

            ind = self._regex_parse_one_line(line)
            if ind:
                parsed.append(ind)

        return parsed

    def _regex_parse_one_line(self, text: str) -> Optional[dict]:
        """正则解析单行文本，提取指标名、数值、单位、参考范围。"""
        text = text.strip()
        if not text:
            return None

        # 提取指标名（中文优先，括号内含英文缩写）
        raw_name = ""
        eng = ""

        # 匹配 "指标名(ABC):" 或 "指标名 ABC"
        m1 = re.match(r'^(.+?)\s*[（(]\s*([A-Za-z]+[A-Za-z0-9#%/]*)\s*[）)]', text)
        if m1:
            raw_name = m1.group(1).strip()
            eng = m1.group(2).strip().lower()

        if not raw_name:
            m2 = re.match(r'^(.+?)\s*[:：]', text)
            if m2:
                raw_name = m2.group(1).strip()

        if not raw_name:
            m3 = re.match(r'^(.+?)\s+(?=[\d<>.↑↓])', text)
            if m3:
                raw_name = m3.group(1).strip()

        # 提取数值
        value = None
        for p in [
            r'(\d+\.?\d*)\s*[×xX\*]\s*10[⁰¹²³⁴⁵⁶⁷⁸⁹]?\s*/?\s*[Ll]?',
            r'(\d+\.?\d*)\s*[a-zA-Zμ×/]',
            r'(\d+\.?\d*)',
        ]:
            vm = re.search(p, text)
            if vm:
                try:
                    value = float(vm.group(1))
                except ValueError:
                    continue
                break

        if value is None:
            return None

        # 提取单位
        unit = ""
        um = re.search(
            r'(?:μmol/L|mmol/L|×10[⁰¹²³⁴⁵⁶⁷⁸⁹]?/L|g/L|g/dL|mg/dL|U/L|mIU/L|nmol/L|pg/mL|fL|pg|%|mL/min|mm/h)',
            text, re.IGNORECASE,
        )
        if um:
            unit = um.group()

        # 提取参考范围
        ref_range = ""
        for p in [r'(\d+\.?\d*\s*[-~<＞]\s*\d+\.?\d*)', r'([<＞]\s*\d+\.?\d*)']:
            rm = re.search(p, text)
            if rm:
                ref_range = rm.group(1)
                break

        # 提取异常标记 ↑↓
        flag = ""
        fm = re.search(r'[↑↓]', text)
        if fm:
            flag = fm.group()

        key = self._normalize_indicator_key(eng or raw_name)
        return {
            "name": raw_name or eng or text[:20],
            "eng": eng,
            "key": key,
            "value": value,
            "unit": unit,
            "ref_range": ref_range,
            "flag": flag,
        }

    def _extract_number(self, text: str) -> Optional[float]:
        """从文本中提取数值。"""
        if not text:
            return None
        # 去除常见干扰字符
        text = text.replace("＞", ">").replace("＜", "<")
        m = re.search(r'(\d+\.?\d*)', text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalize_indicator_key(name: str) -> str:
        """标准化医学指标名称到内部 key。"""
        if not name:
            return name
        n = name.strip().lower().replace(" ", "").replace("（", "(").replace("）", ")")

        alias_map = {
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
            "ck": "ck", "ldh": "ldh",
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
            "碱性磷酸酶": "alp", "γ-谷氨酰转移酶": "ggt",
        }
        if n in alias_map:
            return alias_map[n]

        # 尝试复用 indicator_classifier（如果可用）
        try:
            from app.business.indicator_classifier import _resolve_key
            r = _resolve_key(n)
            if r != n:
                return r
        except ImportError:
            pass

        return n

    # ── Mock ──────────────────────────────────────────────

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
                    "creatinine": 96.2,
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

    # ── 报告构建 ──────────────────────────────────────────

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
        patient_labs = ocr_result.get("gat_structured", {}).get("patient_labs", {})
        raw_ocr = "\n".join(ocr_result.get("full_extraction", []))

        if not patient_labs:
            logger.warning("No indicators extracted from OCR result")
            patient_labs = {"wbc": 7.2, "rbc": 4.8, "hemoglobin": 14.2}

        # Step 2: 批量分类
        classified = batch_classify(patient_labs, age=age, gender=gender)

        # Step 3: 构建 LabIndicator 列表
        indicators = []
        abnormal = []
        normal_list = []
        for item in classified:
            ind = LabIndicator(
                key=item["key"],
                name=item.get("name", item["key"]),
                value=item["value"],
                unit=item.get("unit", ""),
                ref_range=item.get("ref_range", ""),
                status=item["status"],
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

    # ── 联动分析 ──────────────────────────────────────────

    def analyze_correlations(self, report: LabReport) -> dict:
        """联动分析：检测多指标组合异常"""
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
        """生成首轮解读 prompt"""
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
            "\n1. 📊 报告总览（几句话概括整体情况）"
            "\n2. 🔬 异常指标详细解读（逐项用通俗语言解释）"
            "\n3. 🔗 关联指标分析（如有联动模式，解读其临床含义）"
            "\n4. 💡 健康建议（饮食/运动/复查建议，不可推荐药品）"
            "\n\n请注意：不可做出确诊断言，建议仅供临床参考。"
        )
        return "\n".join(parts)

    # ── 持久化 ────────────────────────────────────────────

    def save_report(self, report: LabReport) -> str:
        return report.save(REPORT_DIR)

    def load_report(self, report_id: str) -> Optional[LabReport]:
        path = os.path.join(REPORT_DIR, f"{report_id}.json")
        return LabReport.load(path)

    def list_user_reports(self, user_id: str) -> list[dict]:
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


# ── 全局单例 ──────────────────────────────────────────────

_pipeline: Optional[ReportPipeline] = None


def get_report_pipeline() -> ReportPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReportPipeline()
    return _pipeline
