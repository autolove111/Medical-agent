FROM python:3.11-slim

WORKDIR /app

# 设置 Python 路径
ENV PYTHONPATH=/app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制源代码
COPY . .

# 创建医学文档目录
RUN mkdir -p medical_docs vector_db

# 暴露端口
EXPOSE 8000

# 启动服务（支持热重载用于开发）
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
