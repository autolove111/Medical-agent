"""
OCR 路由

提供 /ocr/recognize 端点。
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ocr", tags=["OCR"])


@router.post("/recognize")
async def ocr_recognize(image_path: str):
    """OCR 识别"""
    try:
        from ocr.paddle_ocr import PaddleOCRWrapper
        ocr = PaddleOCRWrapper()
        result = ocr.recognize(image_path)
        return {"result": result}
    except Exception as e:
        logger.error("OCR recognize failed: %s", e, exc_info=True)
        return {"error": str(e)}
