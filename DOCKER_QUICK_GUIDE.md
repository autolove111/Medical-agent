# 🐳 Docker 启动指南

## 📋 系统要求

- Docker >= 29.0
- Docker Compose >= 5.0
- 至少 4GB 可用内存
- 至少 10GB 可用磁盘空间

## 🚀 快速启动

### 方式 1: 使用脚本启动（推荐）

```bash
cd infrastructure
docker-compose -f docker-compose.yml --env-file ../.env up -d
```

### 方式 2: 查看实时日志启动

```bash
cd infrastructure
docker-compose -f docker-compose.yml --env-file ../.env up
```

### 方式 3: 后台启动加监控

```bash
cd infrastructure
docker-compose up -d
docker-compose logs -f
```

## 📊 服务清单

| 服务              | 端口 | 状态 | 说明          |
| ----------------- | ---- | ---- | ------------- |
| PostgreSQL 数据库 | 5433 | 🟢   | 医学数据存储  |
| Redis 缓存        | 6379 | 🟢   | 会话/缓存管理 |
| LangChain Agent   | 8000 | 🟢   | AI 分析核心   |
| OCR 视觉识别      | 8001 | 🟢   | 化验单识别    |
| Java 后端         | 8080 | 🟢   | 业务逻辑层    |

## ✅ 健康检查

```bash
# LangChain 服务
curl http://localhost:8000/health

# OCR 服务
curl http://localhost:8001/health

# Java 后端
curl http://localhost:8080/api/v1/file/health

# PostgreSQL
docker-compose exec db pg_isready -U postgres

# Redis
docker-compose exec redis redis-cli ping
```

## 🛑 停止服务

```bash
# 只停止容器（保留数据）
docker-compose stop

# 停止并删除容器（保留数据）
docker-compose down

# 完全删除容器和数据卷
docker-compose down -v
```

## 📝 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f medlab-langchain
docker-compose logs -f medlab-ocr
docker-compose logs -f medlab-java-backend

# 查看最后 100 行日志
docker-compose logs -f --tail=100
```

## 🔧 常见命令

```bash
# 查看运行中的容器
docker-compose ps

# 进入容器终端
docker-compose exec medlab-langchain bash

# 重启特定服务
docker-compose restart medlab-langchain

# 查看容器资源使用
docker stats

# 清理未使用的镜像和容器
docker system prune -a
```

## 📍 API 访问

### LangChain Agent 服务

- **主页**: http://localhost:8000/
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

### OCR 视觉识别服务

- **主页**: http://localhost:8001/
- **API 文档**: http://localhost:8001/docs
- **健康检查**: http://localhost:8001/health

### Java 后端服务

- **主页**: http://localhost:8080/
- **Swagger UI**: http://localhost:8080/swagger-ui.html
- **健康检查**: http://localhost:8080/api/v1/file/health

### 数据库连接

- **Host**: localhost
- **Port**: 5433
- **Database**: medlab_db
- **User**: medlab_user
- **Password**: medlab_password

### Redis 连接

- **Host**: localhost
- **Port**: 6379

## 🔐 环境变量配置

关键配置位于 `.env` 文件，包括：

- `DASHSCOPE_API_KEY` - 阿里千问 API 密钥
- `OPENAI_API_KEY` - OpenAI API 密钥（可选）
- `ANTHROPIC_API_KEY` - Claude API 密钥（可选）
  -- `VISION_MODEL` - 视觉模型选择（例如 `qwen3-vl-32b-thinking`）
  -- `DASHSCOPE_MODEL` - LLM 模型选择（例如 `qwen3-vl-32b-thinking`）

## 🐛 故障排除

### 容器启动失败

**表现**: `docker-compose ps` 显示 Exit 或 Dead

**解决**:

```bash
# 查看错误日志
docker-compose logs medlab-langchain

# 删除并重新创建
docker-compose down
docker-compose up -d
```

### 端口被占用

**表现**: `Error: Port already in use`

**解决**:

```bash
# 查看占用端口的进程
netstat -ano | findstr :8000

# 修改 docker-compose.yml 中的端口配置
```

### 数据库连接失败

**表现**: `Connection refused`

**解决**:

```bash
# 检查数据库容器状态
docker-compose logs medlab-db

# 检查网络连接
docker network ls
docker network inspect infrastructure_medlab-network
```

### 内存不足

**表现**: `Exit code 137` 或容器频繁重启

**解决**:

- 增加系统虚拟内存
- 减少其他应用的内存占用
- 修改 `java-backend` 的 `JAVA_OPTS` 参数

## 📚 更多信息

- 详见 `FILE_STRUCTURE.md` - 项目文件结构说明
- 详见 `environment.md` - 环境配置详细说明
- 详见 `API_REFERENCE.md` - API 接口文档

## 🆘 获取帮助

```bash
# 查看 docker-compose 帮助
docker-compose --help

# 查看特定命令帮助
docker-compose up --help
```
