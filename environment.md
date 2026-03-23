# 环境配置说明

MedLabAgent 现在推荐只保留两份环境文件：

- 根目录 `.env`：本机真实配置，不提交 GitHub
- 根目录 `.env.example`：公开模板，可提交 GitHub

不建议继续保留子目录里的 `.env`，例如：

- `langchain_service/.env`
- `infrastructure/.env`

原因很简单：它们和根目录 `.env` 有重复项，而且部分内容已经过时，容易出现“我明明改了配置但服务没生效”的情况。

## 当前生效入口

### 1. 根目录 `.env`
这是整个项目的主环境文件，建议所有真实配置都集中放在这里。

主要包括：

- 大模型密钥：`DASHSCOPE_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`
- 模型配置：`VISION_MODEL`、`DASHSCOPE_MODEL`
- 数据库：`SPRING_DATASOURCE_URL`、`SPRING_DATASOURCE_USERNAME`、`SPRING_DATASOURCE_PASSWORD`、`DATABASE_URL`
- 鉴权：`JWT_SECRET`
- 服务地址：`LANGCHAIN_SERVICE_URL`、`OCR_SERVICE_URL`
- 性能参数：`HTTP_TIMEOUT`、`LLM_API_TIMEOUT`
- Redis：`REDIS_HOST`、`REDIS_PORT`

### 2. Java 配置
Java 通过 [application.yml](/d:/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/resources/application.yml) 读取环境变量。

关键项：

- `spring.servlet.multipart.max-file-size`
- `spring.servlet.multipart.max-request-size`
- `medlab.upload.dir`
- `medlab.server.url`
- `medlab.server.ocr-access-url`
- `langchain.service.url`
- `python-ocr.base-url`

### 3. LangChain 配置
LangChain 通过 [config.py](/d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/config.py) 和 `BaseSettings` 读取 `.env`。

关键项：

- `DASHSCOPE_API_KEY`
- `DASHSCOPE_MODEL`
- `DATABASE_URL`
- `OCR_SERVICE_URL`
- `OCR_SERVICE_TIMEOUT`
- `BACKEND_URL`
- `LANGSMITH_*`

### 4. OCR 配置
OCR 服务通过 [main.py](/d:/Users/xiaoli/Desktop/MedLabAgent/ai-services-python/ocr_service/main.py) 读取环境变量。

关键项：

- `DASHSCOPE_API_KEY`
- `VISION_MODEL`
- `UPLOAD_DIR`
- `REDIS_HOST`
- `REDIS_PORT`
- `HTTP_TIMEOUT`
- `LLM_API_TIMEOUT`
- `OCR_CACHE_TTL_SECONDS`

### 5. Docker 配置
Docker 编排在 [docker-compose.yml](/d:/Users/xiaoli/Desktop/MedLabAgent/infrastructure/docker-compose.yml)。

容器间通信通常使用服务名：

- `python-ocr:8001`
- `python-langchain:8000`
- `redis:6379`
- `db:5432`

本机开发时通常使用：

- `http://localhost:8080`
- `http://localhost:8000`
- `http://localhost:8001`

## 推荐结构

推荐最终只保留：

- [`.env`](/d:/Users/xiaoli/Desktop/MedLabAgent/.env)
- [`.env.example`](/d:/Users/xiaoli/Desktop/MedLabAgent/.env.example)

建议删除：

- [langchain_service/.env](/d:/Users/xiaoli/Desktop/MedLabAgent/langchain_service/.env)
- [infrastructure/.env](/d:/Users/xiaoli/Desktop/MedLabAgent/infrastructure/.env)

## 注意事项

- `.env` 一定不要提交到 GitHub
- `.env.example` 只保留变量名和示例值
- Docker 启动时统一使用：
  `docker compose --env-file ../.env ...`
- 如果将来需要区分环境，优先使用：
  `.env.dev`、`.env.prod`，而不是每个子目录都放一份 `.env`