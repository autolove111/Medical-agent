"""
PaddleOCR FastAPI 服务入口

启动: python paddle_server.py
端口: 8001

端点（兼容原有 OCR 服务格式）:
- POST /api/v1/analyze-vision  识别化验单
- GET  /api/v1/health          健康检查
"""

from __future__ import annotations
import logging
import os
import sys

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

# 确保 ocr_service 目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paddle_ocr import get_paddle_ocr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("paddle_server")

app = FastAPI(title="PaddleOCR Service", version="1.0")

# 全局 OCR 实例（延迟加载）
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        use_gpu = os.getenv("PADDLE_GPU", "false").lower() == "true"
        _ocr = get_paddle_ocr(use_gpu=use_gpu)
    return _ocr


# ---- API 模型 ----

class AnalyzeRequest(BaseModel):
    path: str
    force_recheck: bool = False
    focus_item: Optional[str] = None


# ---- 路由 ----

@app.post("/api/v1/analyze-vision")
async def analyze_vision(request: AnalyzeRequest):
    """
    识别化验单图片

    参数:
        path:          图片本地路径
        force_recheck: 是否强制重新识别（忽略缓存）
    """
    file_path = request.path

    if not os.path.exists(file_path):
        return {
            "cached": False, "analysis": [], "full_extraction": [],
            "gat_structured": {"patient_labs": {}, "base_labs": {}, "ratio_labs": {},
                               "mapped_count": 0, "total_items": 0, "coverage": "0%"},
            "error": f"文件不存在: {file_path}",
        }

    try:
        ocr = _get_ocr()
        result = ocr.recognize(file_path)
        logger.info("OCR success: %d indicators (%s coverage)",
                     result["gat_structured"]["mapped_count"],
                     result["gat_structured"]["coverage"])
        return {"cached": False, "analysis": [], **result}
    except Exception as e:
        logger.error("OCR failed: %s", e, exc_info=True)
        return {
            "cached": False, "analysis": [], "full_extraction": [],
            "gat_structured": {"patient_labs": {}, "base_labs": {}, "ratio_labs": {},
                               "mapped_count": 0, "total_items": 0, "coverage": "0%"},
            "error": f"OCR 识别失败: {e}",
        }


@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "engine": "PaddleOCR (PP-OCRv4)", "gpu": os.getenv("PADDLE_GPU", "false")}


# ---- 启动 ----

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("OCR_PORT", "8001"))
    logger.info("Starting PaddleOCR service on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
