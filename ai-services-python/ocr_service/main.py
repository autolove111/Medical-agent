from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import base64

# 初始化FastAPI应用
app = FastAPI(
    title="MedLabAgent OCR Service",
    description="医疗实验室文字识别（OCR）微服务",
    version="1.0.0"
)

# 配置CORS（跨域资源共享）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """根路由 - 服务信息"""
    return {
        "service": "MedLabAgent OCR Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "ocr": "/api/v1/ocr"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "OCR Service"
    }

@app.post("/api/v1/ocr")
async def perform_ocr(file: UploadFile = File(...)):
    """
    执行光学字符识别（OCR）
    
    职责：
    1. 接收上传的医疗报告图片
    2. 使用OCR模型（如PaddleOCR）进行识别
    3. 返回识别出的医学文本
    
    Args:
        file: 上传的医疗报告图片文件
        
    Returns:
        包含识别文本的JSON响应
    """
    try:
        # 读取上传的文件
        contents = await file.read()
        
        # TODO: 集成PaddleOCR或其他OCR库
        # from paddleocr import PaddleOCR
        # ocr = PaddleOCR(use_angle_cls=True, lang='ch')
        # image = Image.open(io.BytesIO(contents))
        # result = ocr.ocr(np.array(image), cls=True)
        
        # 模拟OCR结果（演示用途）
        mock_result = {
            "血液检查报告": [
                "检查日期：2024年1月",
                "红细胞计数：4.5×10¹²/L",
                "白细胞计数：7.2×10⁹/L",
                "血小板：200×10⁹/L",
                "状态：正常"
            ]
        }
        
        return {
            "status": "success",
            "filename": file.filename,
            "ocr_text": mock_result,
            "confidence": 0.95,
            "message": "OCR recognition completed successfully"
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"OCR processing failed: {str(e)}"
            }
        )

@app.post("/api/v1/ocr-base64")
async def perform_ocr_base64(data: dict):
    """
    基于Base64的OCR识别
    
    Args:
        data: 包含base64编码的图片和元数据
        
    Returns:
        识别结果
    """
    try:
        base64_image = data.get('image')
        if not base64_image:
            return {
                "status": "error",
                "message": "No image data provided"
            }
        
        # 解码Base64图片
        image_data = base64.b64decode(base64_image)
        
        # TODO: 进行OCR处理
        
        return {
            "status": "success",
            "ocr_text": "识别的医学文本内容",
            "confidence": 0.92
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to process base64 image: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
