# MedLabAgent LangChain Service - 启动入口点
# 这个文件导入 core/main.py 中的 FastAPI 应用
# 这样 uvicorn 仍然可以用 `uvicorn main:app` 来启动

from core.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
