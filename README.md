# MedLabAgent System

医疗实验室 AI 智能体系统 - 基于云端大模型的智能医学分析平台

---

## 📦 项目结构

```
MedLabAgent/
├── backend-java/                      # Java Spring Boot 后端服务
│   ├── src/main/java/com/medlab/
│   │   ├── MedLabAgentApplication.java
│   │   ├── agent/                     # AI 智能体
│   │   ├── controller/                # REST API 端点
│   │   │   ├── AgentController.java   # AI 对话、文件上传
│   │   │   └── AuthController.java    # 登录、注册、登出
│   │   ├── service/                   # 业务逻辑
│   │   │   ├── BailianQianwenService.java       # 百炼千问 API 调用
│   │   │   ├── SessionChatService.java          # 会话对话历史管理
│   │   │   ├── UserMedicalService.java          # 用户病历管理
│   │   │   ├── StorageService.java              # 文件存储
│   │   │   ├── KnowledgeService.java            # 知识库检索
│   │   │   └── AuthService.java                 # 身份认证
│   │   ├── repository/                # 数据访问层
│   │   ├── entity/                    # 数据库实体
│   │   │   ├── User.java              # 用户信息、病历、过敏药物
│   │   │   ├── LabReport.java         # 化验单
│   │   │   ├── SessionMessage.java    # 会话对话记录 ⭐ (NEW)
│   │   │   └── KnowledgeRecord.java   # 知识库
│   │   ├── config/                    # 配置类
│   │   └── util/                      # 工具类
│   ├── pom.xml
│   ├── Dockerfile
│   └── src/main/resources/
│       ├── application.yml            # 生产环境配置
│       └── application-h2.yml         # H2 开发环境配置
│
├── frontend-vue/                      # Vue.js + Vite 前端
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow.vue         # 聊天窗口 (多轮对话 ⭐)
│   │   │   ├── ChatMessage.vue        # 消息组件
│   │   │   └── LoadingSpinner.vue     # 加载动画
│   │   ├── services/
│   │   │   └── ApiService.js          # HTTP 请求封装
│   │   ├── stores/
│   │   │   ├── chatStore.js           # 聊天状态管理
│   │   │   └── authStore.js           # 认证状态管理
│   │   ├── router/index.js            # 路由配置
│   │   ├── App.vue
│   │   └── main.js
│   ├── package.json
│   ├── vite.config.js                 # SSE 流式支持配置
│   └── public/
│
├── ai-services-python/                # Python 微服务
│   └── ocr_service/
│       ├── main.py                    # FastAPI OCR 服务
│       ├── requirements.txt
│       └── Dockerfile
│
├── infrastructure/                    # Docker & 初始化脚本
│   ├── docker-compose.yml
│   ├── init.sql                       # PostgreSQL 初始化脚本
│   ├── .env                           # 环境变量配置
│   └── nginx/nginx.conf
│
├── bs.bat / start.bat / quick-start.bat  # 快速启动脚本
└── README.md
```

---

## 🔧 技术栈与版本

### 核心版本

| 组件            | 版本   |
| --------------- | ------ |
| **Java**        | 17     |
| **Spring Boot** | 3.3.5  |
| **Vue**         | 3.5.13 |
| **Vite**        | 6.2.2  |
| **PostgreSQL**  | 15     |
| **Node.js**     | 18+    |

### 后端主要依赖

| 框架/库               | 用途                       |
| --------------------- | -------------------------- |
| Spring Boot 3.3.5     | Web 框架 + 依赖注入        |
| Spring Data JPA       | 数据库 ORM                 |
| Spring Security + JWT | 身份认证 (jjwt 0.12.3)     |
| Spring WebFlux        | 异步响应式编程（SSE 流式） |
| PostgreSQL Driver     | 数据库驱动                 |
| H2 2.2.224            | 开发环境数据库             |
| Lombok                | 代码生成                   |
| Maven                 | 构建工具                   |

### 前端主要依赖

| 框架/库            | 用途          |
| ------------------ | ------------- |
| Vue 3.5.13         | UI 框架       |
| Vite 6.2.2         | 构建工具      |
| Axios 1.7.9        | HTTP 请求     |
| Vue Router 4.5.0   | 路由          |
| Pinia 2.3.0        | 状态管理      |
| markdown-it 14.1.0 | Markdown 渲染 |

### AI 服务

- **主要**: 阿里云百炼/千问（Dashscope API）- qwen3.5-122b-a10b
  - 基于 Spring WebClient + Server-Sent Events 流式调用
- **可选**: Ollama（本地 LLM，docker-compose 支持）
- **可选**: PostgreSQL pgvector（向量知识库）

---

## 📊 核心特性

| 特性                      | 说明                                                                |
| ------------------------- | ------------------------------------------------------------------- |
| **多轮对话上下文** ⭐ NEW | SessionMessage 表 + sessionChatService 存储会话历史，支持多用户隔离 |
| **会话登出清理** ⭐ NEW   | 登出或关闭页面时自动清空该用户的会话对话记录                        |
| **流式响应**              | SSE 支持实时 AI 回复流                                              |
| **JWT 认证**              | 用户登录/注册，Bearer Token                                         |
| **医疗档案**              | 用户永久病历历史 + 过敏药物信息                                     |
| **文件上传**              | 化验单图片上传 + MinIO 存储                                         |
| **OCR 识别**              | Python FastAPI 服务提取文字                                         |
| **知识库**                | PostgreSQL + pgvector (1536-dim) 向量搜索                           |
| **双数据库支持**          | PostgreSQL (生产) 或 H2 (开发)                                      |
| **Docker 部署**           | 完整的 docker-compose 编排                                          |

---

## 🗄️ 数据库实体

| 表                  | 描述                           |
| ------------------- | ------------------------------ |
| `users`             | 用户信息、密码、病历、过敏药物 |
| `lab_reports`       | 化验单文件、OCR 识别文本       |
| `report_items`      | 化验项目（血红蛋白、血糖等）   |
| `session_messages`  | **会话对话历史**（登出时清空） |
| `knowledge_records` | 知识库 + 向量嵌入              |
| ~~`chat_messages`~~ | **已废弃**                     |

---

## 🚀 快速启动

### 方案 A: Docker Compose（推荐）

```bash
cd infrastructure
docker-compose up -d
```

### 方案 B: 本地开发

```bash
# 后端（需 PostgreSQL）
cd backend-java
mvn spring-boot:run

# 前端（新终端）
cd frontend-vue
npm install
npm run dev
```

### 快速脚本

- **`bs.bat`** - 完整编译 + 启动（Java + Node）
- **`start.bat`** - 快速启动（需预先编译）
- **`quick-start.bat`** - Docker Compose 一键启动

---

## 📅 版本信息

**当前版本**: 3.3.5  
**最后更新**: 2026-03-10

**主要更新**:

- ✅ Spring Boot 2.7 → 3.3.5
- ✅ Vue 3.3 → 3.5.13
- ✅ Vite 4.5 → 6.2.2
- ✅ 多轮对话会话历史支持
- ✅ 会话登出自动清理
