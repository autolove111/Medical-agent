# MedLabAgent System - 完整项目结构说明

## 📁 项目目录树

```
MedLabAgent-System/
│
├── 📂 backend-java/                         # Java Spring Boot 后端系统（核心）
│   ├── 📂 src/main/java/com/medlab/
│   │   ├── 📄 MedLabAgentApplication.java   # 应用启动入口
│   │   │
│   │   ├── 📂 agent/
│   │   │   └── 📄 MedicalAgent.java         # AI 智能体接口定义
│   │   │
│   │   ├── 📂 tools/
│   │   │   └── 📄 LabTools.java             # AI 工具箱（数据库查询、API调用等）
│   │   │
│   │   ├── 📂 controller/
│   │   │   └── 📄 AgentController.java      # HTTP API 控制层（REST 端点）
│   │   │
│   │   ├── 📂 service/
│   │   │   ├── 📄 KnowledgeService.java     # 知识库业务服务
│   │   │   └── 📄 StorageService.java       # 文件存储服务
│   │   │
│   │   ├── 📂 repository/
│   │   │   └── 📄 KnowledgeRecordRepository.java  # 知识库 DAO（数据访问）
│   │   │
│   │   ├── 📂 entity/
│   │   │   └── 📄 KnowledgeRecord.java      # 知识库数据库实体
│   │   │
│   │   └── 📂 config/
│   │       ├── 📄 WebConfig.java            # Web 配置（CORS、拦截器）
│   │       └── 📄 RestTemplateConfig.java   # HTTP 客户端配置
│   │
│   ├── 📂 src/main/resources/
│   │   ├── 📄 application.yml               # Spring Boot 核心配置
│   │   └── 📂 templates/                    # HTML 模板（通常为空，前后分离）
│   │
│   ├── 📂 src/test/java/com/medlab/
│   │   └── 📂 controller/
│   │       └── 📄 AgentControllerTest.java  # 单元测试
│   │
│   └── 📄 pom.xml                           # Maven 项目配置文件
│
├── 📂 frontend-vue/                         # Vue.js + Vite 前端
│   ├── 📂 public/                           # 静态资源（favicon 等）
│   │   └── 📄 favicon.ico
│   │
│   ├── 📂 src/
│   │   ├── 📂 assets/
│   │   │   └── 📄 main.css                  # 全局样式
│   │   │
│   │   ├── 📂 components/                   # Vue 组件
│   │   │   ├── 📄 App.vue                   # 根组件
│   │   │   ├── 📄 ChatWindow.vue            # 聊天窗口主组件
│   │   │   ├── 📄 ChatMessage.vue           # 单条消息组件
│   │   │   └── 📄 LoadingSpinner.vue        # 加载动画组件
│   │   │
│   │   ├── 📂 services/
│   │   │   └── 📄 ApiService.js             # API 请求服务模块
│   │   │
│   │   ├── 📂 router/
│   │   │   └── 📄 index.js                  # Vue Router 路由配置
│   │   │
│   │   ├── 📂 stores/
│   │   │   └── 📄 chatStore.js              # Pinia 全局状态管理
│   │   │
│   │   ├── 📄 main.js                       # 前端入口文件
│   │   └── 📄 App.vue                       # 应用根组件
│   │
│   ├── 📄 index.html                        # HTML 主页面
│   ├── 📄 package.json                      # npm 依赖配置
│   ├── 📄 package-lock.json                 # 依赖版本锁定
│   ├── 📄 vite.config.js                    # Vite 构建配置
│   ├── 📄 .gitignore                        # Git 忽略文件
│   └── 📂 src/assets/                       # 资源文件目录
│
├── 📂 ai-services-python/                   # Python 微服务（OCR）
│   └── 📂 ocr_service/
│       ├── 📄 main.py                       # FastAPI 应用程序
│       ├── 📄 requirements.txt               # Python 依赖列表
│       └── 📄 Dockerfile                    # 容器化配置
│
├── 📂 infrastructure/                       # 基础设施和运维配置
│   ├── 📄 docker-compose.yml                # 容器编排配置文件
│   ├── 📄 .env                              # 环境变量配置
│   ├── 📄 init.sql                          # 数据库初始化脚本
│   └── 📂 nginx/
│       └── 📄 nginx.conf                    # Nginx 反向代理配置
│
├── 📄 pom.xml                               # 项目主配置文件
├── 📄 Dockerfile.backend                    # Java 应用容器配置
├── 📄 README.md                             # 项目总体说明文档
├── 📄 PROJECT_STRUCTURE.md                  # 项目结构详细说明（本文件）
├── 📄 .gitignore                            # Git 忽略配置
├── 📄 start.sh                              # Linux/Mac 快速启动脚本
├── 📄 start.bat                             # Windows 快速启动脚本
└── 📂 uploads/                              # 文件上传目录（自动生成）
```

---

## 📌 核心文件职责详解

### Java 后端 (Spring Boot)

#### 1. MedLabAgentApplication.java (应用入口)

```java
@SpringBootApplication
public class MedLabAgentApplication {
    public static void main(String[] args) {
        SpringApplication.run(MedLabAgentApplication.class, args);
    }
}
```

**职责：**

- 启动 Spring Boot 框架
- 初始化所有 Bean
- 扫描并注册所有 Spring 组件

#### 2. agent/MedicalAgent.java (AI 智能体)

**职责：**

- 定义 AI 智能体的核心行为
- 管理系统提示词（System Prompt）
- 协调工具调用和多轮对话

#### 3. tools/LabTools.java (工具箱)

**职责：**

- 提供被 AI 调用的工具方法
- 数据库查询（知识库检索）
- 外部 API 调用（如 OCR 服务）
- 数据验证和转换

#### 4. controller/AgentController.java (API 控制器)

**职责：**

- 接收客户端 HTTP 请求
- 路由到相应的服务处理
- 返回 JSON 格式响应
- 错误处理和异常捕获

**主要 API 端点：**

- `GET /api/v1/health` - 健康检查
- `POST /api/v1/agent/analyze-report` - 分析医疗报告
- `POST /api/v1/agent/chat` - AI 对话
- `POST /api/v1/agent/upload-report` - 上传文件
- `GET /api/v1/knowledge/search` - 知识库搜索

#### 5. service/KnowledgeService.java (知识库服务)

**职责：**

- 知识记录的 CRUD 操作
- 文本向量化处理
- 向量相似度搜索
- 知识库索引维护

#### 6. service/StorageService.java (文件存储)

**职责：**

- 处理文件上传
- 管理存储路径
- 文件安全验证
- 文件删除管理

#### 7. repository/KnowledgeRecordRepository.java (数据访问层)

**职责：**

- 继承 JpaRepository
- 定义自定义查询方法
- 与数据库交互

#### 8. entity/KnowledgeRecord.java (数据实体)

**职责：**

- 映射 `knowledge_records` 表
- 定义数据库字段和约束
- 实体验证规则

#### 9. config/ (配置类)

**WebConfig.java:**

- CORS 跨域配置
- 拦截器设置

**RestTemplateConfig.java:**

- HTTP 客户端配置
- 连接池和超时设置

---

### Vue.js 前端

#### 1. App.vue (根组件)

```vue
<template>
  <div id="app">
    <header>MedLabAgent</header>
    <router-view />
  </div>
</template>
```

**职责：**

- 应用顶级容器
- 包含 router-view 用于页面切换
- 全局样式和布局

#### 2. components/ChatWindow.vue (聊天窗口)

**职责：**

- 显示聊天界面
- 管理消息列表
- 处理用户输入
- 调用 API 与后端交互

#### 3. components/ChatMessage.vue (消息组件)

**职责：**

- 显示单条消息
- 区分用户和 AI 消息
- 时间戳显示

#### 4. components/LoadingSpinner.vue (加载动画)

**职责：**

- 显示加载中状态
- 改善用户体验

#### 5. services/ApiService.js (API 服务)

**职责：**

- 封装所有 HTTP 请求（Axios）
- 处理 EventSource 流式响应
- 统一错误处理
- 请求/响应拦截器

```javascript
export default {
    checkHealth(),      // 健康检查
    analyzeReport(),    // 分析报告
    chat(),             // AI 对话
    uploadReport(),     // 上传文件
    searchKnowledge(),  // 知识库搜索
    streamChat()        // 流式对话
}
```

#### 6. router/index.js (路由配置)

**职责：**

- 定义应用路由
- URL 与组件映射
- 路由导航管理

#### 7. stores/chatStore.js (Pinia 状态管理)

**职责：**

- 管理聊天消息列表
- 管理用户信息
- 管理加载和错误状态
- 全局状态共享

#### 8. main.js (前端入口)

**职责：**

- 创建 Vue 应用实例
- 挂载路由和状态管理
- 初始化全局配置

---

### Python 微服务 (FastAPI)

#### ocr_service/main.py

**职责：**

- FastAPI 应用框架
- 处理 OCR 文字识别请求
- 接收医疗报告图片
- 返回识别的文本内容

**API 端点：**

- `GET /` - 服务信息
- `GET /health` - 健康检查
- `POST /api/v1/ocr` - 执行 OCR
- `POST /api/v1/ocr-base64` - Base64 格式 OCR

---

### 基础设施

#### docker-compose.yml

**服务定义：**

- **postgres** - PostgreSQL 数据库
- **backend** - Java Spring Boot 应用
- **ocr_service** - Python FastAPI 微服务
- **nginx** - 反向代理
- **redis** - 缓存存储
- **ollama** - AI 模型服务

**网络配置：**

- 所有服务连接到 `medlab_network` 网络
- 容器间通过服务名通信

#### init.sql (数据库初始化)

**功能：**

- 创建 pgvector 扩展
- 创建知识库表
- 创建索引
- 插入示例数据

#### nginx.conf (反向代理)

**功能：**

- 统一请求入口（端口 80）
- 路由 `/api/` 到后端
- 路由 `/ocr/` 到 OCR 服务
- 提供静态资源（前端）
- GZIP 压缩
- 静态资源缓存

#### .env (环境变量)

**配置项：**

- 数据库凭证
- 应用端口
- AI 模型地址
- 日志级别

---

## 🔄 请求流程图

```
┌─────────────┐
│  浏览器     │  用户输入问题或上传文件
│  (前端)     │
└──────┬──────┘
       │ HTTP 请求 (JSON)
       ↓
┌────────────────────┐
│   Nginx 80         │  反向代理层
│  (反向代理)        │  - CORS 处理
└──────┬─────────────┘  - 流量分发
       │               - 静态资源缓存
       ├─────────────────────┐
       │                     │
       ↓ /api/               ↓ /ocr/
┌──────────────────┐    ┌──────────────┐
│ Spring Boot      │    │  Python      │
│ :8080            │    │  FastAPI     │
│                  │    │  :8000       │
│ AgentController  │    │              │
│ ├─ health        │    │ ├─ OCR       │
│ ├─ analyze       │    │ ├─ health    │
│ ├─ chat          │    │ └─ ...       │
│ ├─ upload        │    └──────────────┘
│ ├─ search        │
│                  │
│ LabTools         │
│ ├─ queryDB       │
│ ├─ callOCR       │
│ └─ classify      │
│                  │
│ KnowledgeService │
│ ├─ search        │
│ ├─ vectorize     │
│ └─ save          │
└──────┬───────────┘
       │
       ↓
┌─────────────────────────┐
│   PostgreSQL + pgvector │  数据库层
│   :5432                 │
│                         │
│ knowledge_records       │
│ conversations           │
│ user_sessions           │
└─────────────────────────┘

外部服务：
┌──────────────┐    ┌──────────────┐
│  Ollama      │    │   Redis      │
│  :11434      │    │   :6379      │
│              │    │              │
│ AI 模型推理  │    │ 缓存存储     │
└──────────────┘    └──────────────┘
```

---

## 📊 数据库架构

### knowledge_records (知识库表)

```
id (BIGINT, PK)
├─ content (TEXT) - 医学知识内容
├─ source (VARCHAR) - 知识来源
├─ category (VARCHAR) - 知识分类
├─ embedding (vector 1536) - 内容向量化
├─ created_at (TIMESTAMP) - 创建时间
└─ updated_at (TIMESTAMP) - 更新时间

索引：
├─ idx_knowledge_category
├─ idx_knowledge_source
├─ idx_knowledge_created_at
└─ idx_knowledge_embedding (ivfflat - 向量搜索)
```

### medical_conversations (对话记录表)

```
id (BIGINT, PK)
├─ user_id (VARCHAR)
├─ user_query (TEXT)
├─ agent_response (TEXT)
├─ timestamp (TIMESTAMP)
└─ status (VARCHAR)
```

### user_sessions (用户会话表)

```
id (BIGINT, PK)
├─ user_id (VARCHAR, UNIQUE)
├─ session_token (VARCHAR)
├─ created_at (TIMESTAMP)
├─ last_activity (TIMESTAMP)
└─ expires_at (TIMESTAMP)
```

---

## 🚀 启动流程

### Docker Compose 启动顺序

1. **postgres** 首先启动
   - 创建数据库
   - 执行 init.sql
   - 创建表和索引

2. **backend** 依赖 postgres
   - 等待数据库就绪
   - 连接数据库
   - 初始化 Hibernate

3. **ocr_service** 独立启动
   - 初始化 FastAPI
   - 加载 OCR 模型

4. **redis** 独立启动
   - 初始化缓存

5. **ollama** 独立启动
   - 加载 AI 模型

6. **nginx** 依赖后端服务
   - 反向代理配置
   - 等待上游服务

---

## 💡 设计模式

### MVC 架构

- **Model**: Entity + Repository
- **View**: Vue.js 组件
- **Controller**: AgentController

### 分层架构

1. **表现层** (Presentation): Vue.js + Nginx
2. **控制层** (Controller): AgentController
3. **业务层** (Service): KnowledgeService, StorageService
4. **数据层** (Data Access): Repository
5. **数据库层** (Database): PostgreSQL

### 工具模式

- LabTools 为 AI 智能体提供工具接口
- 通过 @Tool 注解标记可调用的方法

### 依赖注入

- 使用 Spring 的 @Autowired 自动注入
- 松耦合，易于单元测试

---

## 📈 扩展建议

### 性能优化

1. 添加 Redis 缓存层
2. 实现数据库连接池优化
3. 向量数据库索引优化
4. API 请求限流

### 功能扩展

1. 集成更多 LLM 模型（GPT, Claude）
2. 支持多语言
3. 添加用户认证和授权
4. 医疗数据合规性审计

### 运维改进

1. 集成 ELK Stack 日志分析
2. Prometheus + Grafana 监控
3. Jenkins CI/CD 自动化
4. Kubernetes 容器编排

---

## 📝 文件大小参考

| 类型        | 数量 | 总大小  |
| ----------- | ---- | ------- |
| Java 源文件 | 10   | ~150 KB |
| Vue 组件    | 5    | ~50 KB  |
| Python 代码 | 1    | ~30 KB  |
| 配置文件    | 8    | ~100 KB |
| 文档        | 2    | ~200 KB |

---

**更新时间**: 2024-01-26  
**版本**: 1.0.0-SNAPSHOT  
**维护者**: MedLabAgent Team
