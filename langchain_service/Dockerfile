# 使用轻量级基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 1. 拷贝依赖定义和本地 torch wheel（利用缓存）
COPY requirements.txt .
COPY torch-2.11.0-cp311-cp311-manylinux_2_28_x86_64.whl /tmp/

# 2. 合并安装步骤
# 安装本地 torch，再安装其他依赖，最后清理
RUN pip install --no-cache-dir --timeout 600 \
    /tmp/torch-2.11.0-cp311-cp311-manylinux_2_28_x86_64.whl \
    --index-url http://mirrors.ustc.edu.cn/pypi/web/simple \
    --trusted-host mirrors.ustc.edu.cn && \
    pip install --no-cache-dir --timeout 600 \
    -r requirements.txt \
    --index-url http://mirrors.ustc.edu.cn/pypi/web/simple \
    --trusted-host mirrors.ustc.edu.cn && \
    rm /tmp/torch-2.11.0-cp311-cp311-manylinux_2_28_x86_64.whl

# 3. 创建必要的目录
RUN mkdir -p medical_docs vector_db

# 4. 拷贝源代码（最后拷贝，代码变动最频繁）
COPY . .

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]