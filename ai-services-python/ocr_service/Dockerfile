ARG PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-bookworm
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

# 安装系统依赖（包括 curl 用于健康检查）
RUN apt-get update -o Acquire::Retries=5 && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖 - 包含 httpx 用于零延迟异步调用
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露异步服务端口
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 启动异步应用（使用 uvicorn 执行 main.py）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
