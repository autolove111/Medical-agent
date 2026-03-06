# MedLabAgent System - 医疗实验室AI智能体系统

## 📋 项目概述

MedLabAgent 是一个企业级的**医疗实验室AI智能体系统**，致力于通过人工智能技术辅助医疗专业人士进行医学检查报告的分析和诊断建议。

### 核心功能

- 🤖 **AI 智能体** - 基于 LangChain4j 和 Ollama 的医疗AI智能体
- 📄 **文本识别** - Python FastAPI 微服务进行 OCR 医疗报告识别
- 💬 **智能对话** - 支持多轮医学知识对话
- 📚 **知识库** - PostgreSQL + pgvector 的向量知识库
- 🎨 **现代UI** - Vue.js + Vite 前端界面

---

## 🏗️ 技术架构

### 项目结构

```
MedLabAgent/
├── backend-java/               # Java Spring Boot 后端（主要系统）
│   ├── src/main/java/com/medlab/
│   │   ├── MedLabAgentApplication.java   # 应用入口
│   │   ├── agent/MedicalAgent.java       # AI智能体
│   │   ├── tools/LabTools.java           # 工具箱
│   │   ├── controller/                   # HTTP API 控制层
│   │   ├── service/                      # 业务服务层
│   │   ├── repository/                   # 数据访问层
│   │   ├── entity/                       # 数据库实体
│   │   └── config/                       # 配置类
│   ├── pom.xml                           # Maven 依赖管理
│   └── ...
│
├── frontend-vue/               # Vue.js + Vite 前端
│   ├── src/
│   │   ├── components/         # Vue 组件
│   │   ├── services/           # API 服务模块
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── router/             # 路由配置
│   │   └── ...
│   ├── package.json
│   ├── vite.config.js
│   └── ...
│
├── ai-services-python/         # Python 微服务
│   └── ocr_service/
│       ├── main.py             # FastAPI 应用
│       ├── requirements.txt
│       └── Dockerfile
│
├── infrastructure/             # 基础设施配置
│   ├── docker-compose.yml      # 容器编排
│   ├── .env                    # 环境变量
│   ├── init.sql                # 数据库初始化
│   └── nginx/nginx.conf        # 反向代理配置
│
├── pom.xml                     # 主项目 Maven 配置
├── Dockerfile.backend          # Java 应用容器配置
└── README.md                   # 项目说明文档
```

---

## 🛠️ 技术栈

### 后端 (Java)

- **框架**: Spring Boot 3.1.5
- **ORM**: Spring Data JPA + Hibernate
- **数据库**: PostgreSQL 15 + pgvector（向量数据库）
- **AI**: LangChain4j 0.27.1 + Ollama
- **HTTP 客户端**: RestTemplate
- **构建工具**: Maven 3.9.4
- **Java 版本**: JDK 17

### 前端 (Vue.js)

- **框架**: Vue 3.3.4
- **构建工具**: Vite 4.5.0
- **HTTP 客户端**: Axios 1.5.0
- **路由**: Vue Router 4.2.5
- **状态管理**: Pinia 2.1.6
- **样式**: CSS3 (无需第三方框架)

### Python 微服务

- **框架**: FastAPI 0.104.1
- **服务器**: Uvicorn 0.24.0
- **OCR**: PaddleOCR 2.7.0
- **图像处理**: Pillow 10.0.0

### 基础设施

- **容器化**: Docker + Docker Compose
- **数据库**: PostgreSQL 15
- **缓存**: Redis 7
- **反向代理**: Nginx (Alpine)
- **AI 模型**: Ollama

---

## 📦 快速开始

### 前置要求

- Docker & Docker Compose (推荐用于生产环境)
- JDK 17+ (本地开发)
- Maven 3.9.4+ (本地构建)
- Node.js 18+ (前端开发)
- PostgreSQL 15+ (如不使用 Docker)

### 方案 A: 使用 Docker Compose (推荐 - 一键启动)

#### 1. 配置环境变量

```bash
cd infrastructure
# .env 文件已包含默认配置，可直接使用或根据需要修改
cat .env
```

#### 2. 启动所有服务

```bash
cd infrastructure
docker-compose up -d
```

**服务启动后的地址：**

- 🌐 **前端**: http://localhost/ (需要先构建前端并放入 nginx)
- 🔌 **后端 API**: http://localhost:8080/api/v1
- 📝 **OCR 服务**: http://localhost:8000/api/v1/ocr
- 🗄️ **数据库**: localhost:5432
- 💾 **Redis**: localhost:6379
- 🤖 **Ollama**: http://localhost:11434

#### 3. 验证服务状态

```bash
# 检查所有容器状态
docker-compose ps

# 查看后端日志
docker-compose logs -f backend

# 查看数据库日志
docker-compose logs -f postgres
```

#### 4. 停止所有服务

```bash
docker-compose down
```

---

### 方案 B: 本地开发（分别启动各个组件）

#### 后端 (Java)

```bash
# 1. 进入项目根目录
cd MedLabAgent

# 2. 确保 PostgreSQL 运行
# 连接字符串: jdbc:postgresql://localhost:5432/medlab_db
# 用户名: medlab_user
# 密码: medlab_password

# 3. 构建项目
mvn clean install

# 4. 启动应用
mvn spring-boot:run

# 服务将在 http://localhost:8080 启动
```

#### 前端 (Vue.js)

```bash
# 1. 进入前端目录
cd frontend-vue

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev

# 访问: http://localhost:5173
# 自动代理到后端 API
```

#### Python OCR 服务

```bash
# 1. 进入 OCR 服务目录
cd ai-services-python/ocr_service

# 2. 创建虚拟环境（可选）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
python main.py

# 服务将在 http://localhost:8000 启动
```

---

## 📝 API 文档

### 后端 API

#### 健康检查

```bash
GET /api/v1/health

Response:
{
  "status": "UP",
  "message": "MedLabAgent System is running"
}
```

#### 分析医疗报告

```bash
POST /api/v1/agent/analyze-report?reportContent=<报告内容>

Response:
{
  "status": "success",
  "analysis": "AI分析结果"
}
```

#### AI 对话

```bash
POST /api/v1/agent/chat?userQuery=<用户问题>

Response:
{
  "status": "success",
  "response": "AI回答"
}
```

#### 上传医疗报告

```bash
POST /api/v1/agent/upload-report
Content-Type: multipart/form-data

Body:
file: <医疗报告文件>

Response:
{
  "status": "success",
  "filePath": "uploads/uuid_filename",
  "fileName": "report.pdf"
}
```

#### 搜索知识库

```bash
GET /api/v1/knowledge/search?keyword=<关键词>

Response:
{
  "status": "success",
  "results": [...],
  "count": 3
}
```

### Python OCR API

#### 执行 OCR 识别

```bash
POST http://localhost:8000/api/v1/ocr
Content-Type: multipart/form-data

Body:
file: <医疗报告图片>

Response:
{
  "status": "success",
  "filename": "report.jpg",
  "ocr_text": {
    "血液检查报告": ["检查日期...", "红细胞计数..."]
  },
  "confidence": 0.95
}
```

---

## 🗄️ 数据库说明

### 初始化

数据库初始化脚本位于 `infrastructure/init.sql`，会自动在 PostgreSQL 容器启动时执行，包括：

1. **创建 pgvector 扩展** - 支持向量相似度搜索
2. **创建知识库表** - `knowledge_records`
3. **创建索引** - 提升查询性能
4. **插入示例数据** - 医学知识样本

### 主要表结构

#### knowledge_records（知识库）

```sql
- id: 主键
- content: 知识内容（TEXT）
- source: 知识来源
- category: 知识分类
- embedding: 向量嵌入 (vector 1536)
- created_at: 创建时间
- updated_at: 更新时间
```

#### medical_conversations（对话记录）

```sql
- id: 主键
- user_id: 用户ID
- user_query: 用户问题
- agent_response: AI回答
- timestamp: 时间戳
- status: 状态
```

---

## 🔧 配置说明

### application.yml（Java 应用配置）

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/medlab_db
    username: medlab_user
    password: medlab_password

  jpa:
    hibernate:
      ddl-auto: update # update/create/create-drop/validate

ai:
  ollama:
    base-url: http://localhost:11434
    model: llama2
    temperature: 0.7
    max-tokens: 1000
```

### .env（Docker 环境变量）

位于 `infrastructure/.env`，包含数据库、应用、AI 服务等配置。

---

## 📊 系统流程图

```
用户请求 (前端)
    ↓
Nginx (反向代理)
    ↓
Spring Boot 后端 (Java)
    ├→ AgentController (接收请求)
    ├→ MedicalAgent (AI 处理)
    ├→ LabTools (工具调用)
    ├→ KnowledgeService (知识库查询)
    └→ StorageService (文件处理)
    ↓
PostgreSQL + pgvector (知识库存储)

外部服务：
- Ollama (AI 模型推理)
- Python OCR Service (文字识别)
- Redis (缓存)
```

---

## 🚀 部署

### 生产环境部署

```bash
# 1. 构建镜像
docker-compose build

# 2. 启动服务（后台运行）
docker-compose up -d

# 3. 查看状态
docker-compose ps

# 4. 查看日志
docker-compose logs -f backend

# 5. 停止服务
docker-compose stop

# 6. 重启服务
docker-compose restart
```

### 性能优化建议

1. **数据库优化**
   - 为频繁查询的字段创建索引
   - 使用连接池 (HikariCP)
   - 定期分析和优化查询

2. **缓存策略**
   - 使用 Redis 缓存热点数据
   - 实现查询结果缓存
   - 设置合理的过期时间

3. **API 优化**
   - 实现请求限流
   - 启用 GZIP 压缩
   - 使用 CDN 分发静态资源

4. **监控和日志**
   - 集成 ELK Stack (Elasticsearch, Logstash, Kibana)
   - 监控系统资源使用
   - 记录关键操作日志

---

## 🧪 测试

### 运行单元测试

```bash
# 后端测试
mvn test

# 前端测试（如配置）
npm run test
```

### 集成测试

```bash
# 使用 Docker Compose 启动所有服务
docker-compose up -d

# 运行测试套件
mvn verify
```

---

## 📚 文件说明

### Java 后端主要文件

| 文件                             | 职责                             |
| -------------------------------- | -------------------------------- |
| `MedLabAgentApplication.java`    | 应用入口，@SpringBootApplication |
| `MedicalAgent.java`              | AI 智能体接口                    |
| `LabTools.java`                  | AI 工具箱，被 Agent 调用         |
| `AgentController.java`           | HTTP API 控制层                  |
| `KnowledgeService.java`          | 知识库业务逻辑                   |
| `StorageService.java`            | 文件存储服务                     |
| `KnowledgeRecord.java`           | 知识库实体                       |
| `KnowledgeRecordRepository.java` | 知识库数据访问                   |

### 前端主要文件

| 文件                 | 职责           |
| -------------------- | -------------- |
| `App.vue`            | 根组件         |
| `ChatWindow.vue`     | 聊天窗口主组件 |
| `ChatMessage.vue`    | 单条消息组件   |
| `LoadingSpinner.vue` | 加载动画组件   |
| `ApiService.js`      | API 请求封装   |
| `chatStore.js`       | Pinia 状态管理 |
| `router/index.js`    | 路由配置       |

---

## 🆘 故障排查

### 常见问题

#### 1. PostgreSQL 连接失败

```
错误: jdbc:postgresql://localhost:5432/medlab_db refused
```

**解决方案:**

- 确保 PostgreSQL 容器正在运行: `docker-compose ps`
- 检查密码和用户名是否正确
- 检查网络连接: `docker-compose logs postgres`

#### 2. 前端无法连接到后端

```
CORS 错误或 API 404
```

**解决方案:**

- 检查后端是否运行: `curl http://localhost:8080/api/v1/health`
- 验证 vite.config.js 中的代理配置
- 检查 WebConfig.java 中的 CORS 设置

#### 3. OCR 服务 500 错误

```
OCR processing failed
```

**解决方案:**

- 检查 PaddleOCR 是否正确安装
- 查看 Python 服务日志: `docker-compose logs ocr_service`
- 确保上传的文件格式正确 (jpg, png, pdf)

#### 4. Maven 编译失败

```
[ERROR] Failed to compile
```

**解决方案:**

```bash
# 清除缓存
mvn clean

# 重新下载依赖
mvn install -U

# 检查 Java 版本
java -version  # 应为 17+
```

---

## 🤝 贡献指南

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 📞 联系方式

- 📧 Email: support@medlab.ai
- 🐛 Issue: [GitHub Issues](https://github.com/medlab/agent/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/medlab/agent/discussions)

---

## 🙏 致谢

感谢所有为本项目做出贡献的开发者和医疗专业人士。

---

## 📌 更新日志

### v1.0.0 (2024-01-26)

- ✅ 初始版本发布
- ✅ 核心 AI 智能体功能
- ✅ OCR 文字识别服务
- ✅ 知识库管理系统
- ✅ Web UI 界面
- ✅ Docker 容器化部署

---

**最后更新**: 2024-01-26  
**维护者**: MedLabAgent Team
