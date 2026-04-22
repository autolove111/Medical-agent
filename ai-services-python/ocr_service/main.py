#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OCR 服务：远程视觉识别 + Redis 缓存
遵循"上传即预热，分析时命中缓存"的设计原则

流程：
1. 收到 path → 查 Redis 缓存
2. 缓存命中 → 直接返回（<100ms）
3. 缓存未命中 → 下载图片 → base64 → 调 DashScope qwen3-vl-32b-thinking → 结构化 → 写缓存 → 返回
"""

import hashlib
import json
import logging
import os
import re
import asyncio
from typing import Any, Dict, Optional
import httpx
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from io import BytesIO
try:
    from PIL import Image
except Exception:
    Image = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 配置 ====================
DASHSCOPE_API_KEY = "sk-"  # 从环境变量读取
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_MODEL = os.getenv("VISION_MODEL", "qwen3-vl-32b-thinking")
REDIS_HOST = "redis"
REDIS_PORT = 6379
REDIS_TTL = 86400 * 7  # 7 天缓存

# ==================== 医学指标映射 ====================
_INDICATOR_ALIAS = {
    "wbc": ["白细胞计数", "WBC", "白血球"],
    "rbc": ["红细胞计数", "RBC", "红血球"],
    "hemoglobin": ["血红蛋白", "HB", "Hb", "HGB"],
    "hematocrit": ["血细胞比容", "HCT"],
    "mcv": ["平均红细胞体积", "MCV"],
    "mch": ["平均红细胞血红蛋白含量", "MCH"],
    "mchc": ["平均红细胞血红蛋白浓度", "MCHC"],
    "plt": ["血小板计数", "PLT"],
    # ========== 白细胞分类 ==========
    "ne": ["中性粒细胞比值", "NE#", "NE%", "中性粒细胞"],
    "ly": ["淋巴细胞比值", "LY#", "LY%", "淋巴细胞"],
    "mo": ["单核细胞比值", "MO#", "MO%", "单核细胞"],
    "eo": ["嗜酸粒细胞比值", "EO#", "EO%", "嗜酸粒"],
    "ba": ["嗜碱粒细胞比值", "BA#", "BA%", "嗜碱粒"],
    # ========== 红细胞分类 ==========
    "nrbc": ["有核红细胞", "NRBC#", "NRBC%"],
    "rdw": ["红细胞分布宽度", "RDW"],
    # ========== 血小板相关 ==========
    "mpv": ["平均血小板体积", "MPV"],
    "pct": ["血小板压积", "PCT"],
    "pdw": ["血小板分布宽度", "PDW"],
    # ========== 生化指标 ==========
    "glucose": ["葡萄糖", "血糖", "GLU"],
    "bun": ["尿素氮", "BUN"],
    "creatinine": ["肌酐", "CREA", "Cr"],
    "uric_acid": ["尿酸", "UA"],
    "alt": ["丙氨酸氨基转移酶", "ALT", "SGPT"],
    "ast": ["天冬氨酸氨基转移酶", "AST", "SGOT"],
    "alp": ["碱性磷酸酶", "ALP"],
    "total_bilirubin": ["总胆红素", "TBIL"],
    "direct_bilirubin": ["直接胆红素", "DBIL"],
    "sodium": ["钠", "Na"],
    "potassium": ["钾", "K"],
    "chloride": ["氯", "Cl"],
    "calcium": ["钙", "Ca"],
    "phosphorus": ["磷", "P"],
    "magnesium": ["镁", "Mg"],
    "cholesterol": ["胆固醇", "CHO"],
    "triglyceride": ["甘油三酯", "TG"],
    # ========== 蛋白质代谢 ==========
    "total_protein": ["总蛋白", "TP"],
    "albumin": ["白蛋白", "ALB"],
    "globulin": ["球蛋白", "GLO"],
    "a_g_ratio": ["白球比", "A/G"],
    # ========== 胆汁和肝脏 ==========
    "total_bile_acid": ["总胆汁酸", "TBA"],
    "cholinesterase": ["胆碱酯酶", "CHE"],
    "ggt": ["γ-谷氨酰转肽酶", "GGT"],
    # ========== 心肌酶 ==========
    "creatine_kinase": ["肌酸激酶", "CK"],
    "ldh": ["乳酸脱氢酶", "LDH"],
    "a_hbd": ["α-羟基丁酸脱氢酶", "α-HBD", "HBDH"],
    # ========== 肾功能扩展 ==========
    "urea": ["尿素", "UREA"],
    "cystatin_c": ["胱抑素C", "CysC"],
    # ========== 酸碱平衡 ==========
    "co2": ["二氧化碳", "CO2"],
}

# ==================== 工具函数 ====================

def _normalize_indicator_key(text: str) -> Optional[str]:
    """标准化医学指标名称（精确匹配优先，避免比值项误匹配覆盖）。"""
    if not text:
        return None

    def _clean(v: str) -> str:
        s = v.lower().strip()
        s = s.replace("（", "(").replace("）", ")")
        s = re.sub(r"^[*★#\s]+", "", s)
        s = re.sub(r"\s+", "", s)
        return s

    raw = _clean(text)
    # 主体名与括号内别名同时参与匹配，如 "丙氨酸氨基转移酶(ALT)"
    base = _clean(raw.split("(", 1)[0]) if "(" in raw else raw
    bracket = ""
    if "(" in raw and ")" in raw:
        bracket = _clean(raw.split("(", 1)[1].split(")", 1)[0])
    candidates = {c for c in [raw, base, bracket] if c}

    for key, aliases in _INDICATOR_ALIAS.items():
        key_norm = _clean(key)
        alias_norms = {_clean(alias) for alias in aliases}
        if key_norm in candidates or candidates.intersection(alias_norms):
            return key
    return None


def _is_ratio_indicator(text: str) -> bool:
    """判断是否比值/派生指标，单独入表避免污染基础检验值。"""
    if not text:
        return False
    t = text.lower().strip().replace("（", "(").replace("）", ")")
    ratio_tokens = ["/", "比", "ratio", "ast/alt", "a/g"]
    return any(tok in t for tok in ratio_tokens)


def _normalize_ratio_key(text: str) -> str:
    t = text.lower().strip().replace("（", "(").replace("）", ")")
    t = re.sub(r"^[*★#\s]+", "", t)
    if "ast/alt" in t or "天门冬氨酸/丙氨酸" in t:
        return "ast_alt_ratio"
    if "a/g" in t or "白球比" in t:
        return "a_g_ratio"
    return t


def _extract_numeric_value(text: str) -> Optional[float]:
    """从文本中提取数值"""
    import re
    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _build_structured_payload(llm_analysis: str) -> Dict[str, Any]:
    """
    将原始 LLM 分析转换为结构化三层输出：
    - analysis: 原始文本分析
    - full_extraction: 完整内容提取
    - gat_structured: GAT 图处理结果 + 标准化 patient_labs
    """
    lines = llm_analysis.split("\n")
    base_labs = {}
    ratio_labs = {}
    unified_patient_labs = {}
    full_extraction = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 尝试解析 "指标名: 数值 单位" 格式
        if ":" in line:
            parts = line.split(":", 1)
            key_part = parts[0].strip()
            value_part = parts[1].strip() if len(parts) > 1 else ""
            
            numeric_value = _extract_numeric_value(value_part)

            if numeric_value is not None and _is_ratio_indicator(key_part):
                ratio_key = _normalize_ratio_key(key_part)
                ratio_labs[ratio_key] = numeric_value
                full_extraction.append(f"{key_part}: {value_part}")
                continue

            normalized_key = _normalize_indicator_key(key_part)

            if normalized_key and numeric_value is not None:
                base_labs[normalized_key] = numeric_value
                full_extraction.append(f"{key_part}: {value_part}")
            else:
                full_extraction.append(line)
        else:
            full_extraction.append(line)

    # 统一转换为现有下游格式：基础检验优先，比值类仅按白球比等安全映射回填。
    unified_patient_labs.update(base_labs)
    if "a_g_ratio" in ratio_labs and "a_g_ratio" not in unified_patient_labs:
        unified_patient_labs["a_g_ratio"] = ratio_labs["a_g_ratio"]

    logger.info(
        "✓ 结构化指标提取完成: base_labs=%s (共 %d), ratio_labs=%s (共 %d), unified_patient_labs=%s (共 %d)",
        base_labs,
        len(base_labs),
        ratio_labs,
        len(ratio_labs),
        unified_patient_labs,
        len(unified_patient_labs),
    )
    return {
        "analysis": [line.strip() for line in lines if line.strip()],
        "full_extraction": full_extraction,
        "gat_structured": {
            "patient_labs": unified_patient_labs,
            "base_labs": base_labs,
            "ratio_labs": ratio_labs,
            "mapped_count": len(unified_patient_labs),
            "total_items": len(full_extraction),
            "coverage": f"{len(unified_patient_labs) * 100 // max(1, len(full_extraction))}%" if full_extraction else "0%",
        },
    }


# ==================== Redis 操作 ====================

def _get_redis_client() -> redis.Redis:
    """获取 Redis 客户端"""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=5,
    )


def _get_cache_key(file_path: str) -> str:
    """生成缓存 key"""
    return f"ocr_result:{hashlib.md5(file_path.encode()).hexdigest()}"


def _read_cache(file_path: str) -> Optional[Dict[str, Any]]:
    """从 Redis 读结果"""
    try:
        redis_client = _get_redis_client()
        cache_key = _get_cache_key(file_path)
        cached = redis_client.get(cache_key)
        if cached:
            logger.info("✓ Redis 缓存命中: %s", file_path)
            return json.loads(cached)
    except Exception as e:
        logger.warning("Redis 读取失败: %s", e)
    return None


def _write_cache(file_path: str, result: Dict[str, Any]) -> bool:
    """写入 Redis 缓存"""
    try:
        redis_client = _get_redis_client()
        cache_key = _get_cache_key(file_path)
        redis_client.setex(cache_key, REDIS_TTL, json.dumps(result))
        logger.info("✓ 结果已写入 Redis: %s", file_path)
        return True
    except Exception as e:
        logger.warning("Redis 写入失败: %s", e)
    return False


# ==================== 视觉识别 ====================

async def _call_dashscope_vision(image_base64: str) -> str:
    """调用 DashScope qwen3-vl-32b-thinking 识别图片（支持 Mock 模式）"""
    import os
    api_key = os.getenv("DASHSCOPE_API_KEY", "")
    use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"
    
    # Mock 模式：返回模拟 OCR 结果
    if use_mock or not api_key or api_key.strip() in ("sk-", ""):
        logger.info("⚠️ 使用 Mock OCR 模式（无需真实 API key）")
        return (
            "【OCR Mock 模式识别结果】\n\n"
            "患者信息：李某某\n"
            "检验日期：2026-04-03\n"
            "检验类型：体检套餐\n\n"
            "【血液学检查】\n"
            "白细胞计数(WBC)：7.2 × 10³/μL 参考值：4.5-11.0 状态：正常\n"
            "红细胞计数(RBC)：4.8 × 10⁶/μL 参考值：4.5-5.9 状态：正常\n"
            "血红蛋白(HB)：14.2 g/dL 参考值：13.0-16.0 状态：正常\n"
            "血小板计数(PLT)：250 × 10³/μL 参考值：150-400 状态：正常\n\n"
            "【肝功能检查】\n"
            "丙氨酸氨基转移酶(ALT)：28 U/L 参考值：<40 状态：正常\n"
            "天冬氨酸氨基转移酶(AST)：32 U/L 参考值：<40 状态：正常\n"
            "碱性磷酸酶(ALP)：72 U/L 参考值：45-120 状态：正常\n"
            "总胆红素(TBIL)：0.8 mg/dL 参考值：<1.2 状态：正常\n\n"
            "【肾功能检查】\n"
            "肌酐(CREA)：0.85 mg/dL 参考值：0.7-1.3 状态：正常\n"
            "尿素氮(BUN)：16 mg/dL 参考值：7-20 状态：正常\n"
            "尿酸(UA)：5.2 mg/dL 参考值：3.5-7.2 状态：正常\n"
        )
    
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": DASHSCOPE_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "请分析这张医学检验单，提取所有化验指标名称和对应数值。"
                            "格式：指标名: 数值 单位\n"
                            "逐行列出所有检验项和结果。"
                        ),
                    },
                ],
            }
        ],
        "temperature": 0.5,
    }
    
    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
        last_exc = None
        response = None
        for attempt in range(1, 4):
            try:
                response = await client.post(
                    f"{DASHSCOPE_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                break
            except httpx.RequestError as e:
                last_exc = e
                logger.warning("DashScope 请求第 %d 次尝试失败: %s", attempt, str(e))
                if attempt < 3:
                    await asyncio.sleep(1 * attempt)
                continue

        if response is None:
            logger.error("DashScope 调用全部尝试失败: %s", str(last_exc))
            raise last_exc

    # 检查 HTTP 响应状态并记录响应体以便排查
    try:
        if response.status_code >= 400:
            logger.error("DashScope 调用失败: status=%s body=%s", response.status_code, response.text)
        response.raise_for_status()
    except Exception as e:
        logger.error("DashScope HTTP 错误: %s; body=%s", str(e), getattr(response, 'text', '<no-body>'))
        raise

    # 解析 JSON 响应，兼容非 JSON 或异常返回
    try:
        result = response.json()
    except Exception as e:
        logger.error("解析 DashScope 返回 JSON 失败: %s; raw=%s", str(e), response.text[:2000] if hasattr(response, 'text') else '<no-body>')
        raise

    if "choices" not in result or not result["choices"]:
        logger.error("DashScope 返回无效结构: %s", json.dumps(result)[:2000])
        raise ValueError("DashScope 返回无效响应")

    return result["choices"][0]["message"]["content"]


async def _download_image_as_base64(image_url: str) -> str:
    """下载图片并转为 base64"""
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get(image_url)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    content_len = len(response.content or b"")
    logger.info("Downloaded image: url=%s content-type=%s size=%d", image_url, content_type, content_len)

    # 基本校验：必须是图片且有足够字节数
    if not content_type.lower().startswith("image/") or content_len < 1000:
        raise ValueError(f"下载到的资源不是有效图片: content_type={content_type} size={content_len}")

    import base64
    content_bytes = response.content

    # 尝试压缩/缩放图片以减少请求体大小，降低被远端断开连接的风险
    if Image is not None:
        try:
            img = Image.open(BytesIO(content_bytes))
            max_dim = 1600
            img.thumbnail((max_dim, max_dim))
            out = BytesIO()
            img.save(out, format="JPEG", quality=75, optimize=True)
            compressed = out.getvalue()
            logger.info("Image compressed: original=%d compressed=%d", len(content_bytes), len(compressed))
            content_bytes = compressed
        except Exception as e:
            logger.warning("图片压缩失败，使用原始字节: %s", e)

    return base64.b64encode(content_bytes).decode("utf-8")


# ==================== FastAPI 应用 ====================

app = FastAPI(title="OCR Service", version="1.0")


class AnalyzeVisionRequest(BaseModel):
    path: str
    force_recheck: bool = False
    focus_item: Optional[str] = None


@app.post("/api/v1/analyze-vision")
async def analyze_vision(request: AnalyzeVisionRequest) -> Dict[str, Any]:
    """
    识别化验单图片
    
    参数：
    - path: 图片路径或 URL
    - force_recheck: 是否强制重新识别（绕过缓存）
    - focus_item: 重点检查项（可选）
    """
    try:
        file_path = request.path
        
        # 查缓存
        if not request.force_recheck:
            cached_result = _read_cache(file_path)
            if cached_result:
                           # 【缓存命中时的日志】
                logger.info("📦 缓存命中 - 提取指标: %s", 
                           cached_result.get("gat_structured", {}).get("patient_labs", {}))
                return {
                    "cached": True,
                    "analysis": cached_result.get("analysis", []),
                    "full_extraction": cached_result.get("full_extraction", []),
                    "gat_structured": cached_result.get("gat_structured", {}),
                }
        
        # 下载图片
        logger.info("正在下载图片: %s", file_path)
        image_base64 = await _download_image_as_base64(file_path)
        
        # 调用 DashScope
        logger.info("正在调用 DashScope qwen3-vl-32b-thinking...")
        llm_analysis = await _call_dashscope_vision(image_base64)
        
        # 结构化处理
        structured = _build_structured_payload(llm_analysis)

                # 【新识别时的日志】
        logger.info("🆕 新识别完成 - 提取指标: %s (coverage: %s)", 
                   structured["gat_structured"]["patient_labs"],
                   structured["gat_structured"]["coverage"])
        
        # 写缓存
        _write_cache(file_path, structured)
        
        logger.info(
            "✓ OCR 完成：文本长度=%d，提取指标=%d",
            len("\n".join(structured["analysis"])),
            len(structured["gat_structured"]["patient_labs"]),
        )
        
        return {
            "cached": False,
            **structured,
        }
    
    except Exception as e:
        logger.error("OCR 分析失败: %s", e, exc_info=True)
        # 返回结构化空结果而不是抛出 500，避免上游流程中断。
        # 包含 error 字段以便上游记录并提示需要复核。
        error_msg = str(e)
        logger.warning("OCR 返回空结构化结果 (error masked to caller): %s", error_msg)
        return {
            "cached": False,
            "analysis": [],
            "full_extraction": [],
            "gat_structured": {
                "patient_labs": {},
                "base_labs": {},
                "ratio_labs": {},
                "mapped_count": 0,
                "total_items": 0,
                "coverage": "0%",
            },
            "error": f"OCR 分析失败: {error_msg}",
        }


@app.get("/api/v1/health")
async def health_check() -> Dict[str, str]:
    """健康检查"""
    try:
        redis_client = _get_redis_client()
        redis_client.ping()
        return {"status": "healthy", "redis": "ok"}
    except Exception as e:
        logger.warning("Redis 连接失败: %s", e)
        return {"status": "healthy", "redis": "unavailable"}


@app.get("/api/v1/models")
async def list_models() -> Dict[str, list]:
    """列出支持的模型"""
    return {
        "models": [DASHSCOPE_MODEL],
        "default": DASHSCOPE_MODEL,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
