# MedLabAgent 项目结构指南

> 医疗实验室 AI 智能体系统 — 项目目录与文件说明

---

## 一、系统架构概览

```
用户 ──→ Vue 3 前端 ──→ Nginx 反向代理 ──→ Spring Boot 后端 ──┬──→ 百炼千问 AI 大模型（流式 SSE）
                                                              ├──→ PostgreSQL + pgvector（数据存储与向量检索）
                                                              └──→ Python OCR 微服务（检验报告图片识别）
```

---

## 二、顶层目录 `MedLabAgent/`

| 文件 / 文件夹              | 说明                                             |
| -------------------------- | ------------------------------------------------ |
| `backend-java/`            | Java Spring Boot 后端服务                        |
| `frontend-vue/`            | Vue 3 前端单页应用                               |
| `ai-services-python/`      | Python AI 微服务（OCR 图片识别）                 |
| `infrastructure/`          | 基础设施配置（数据库初始化、Nginx、Docker 编排） |
| `logs/`                    | 运行时日志输出目录                               |
| `target/`                  | Maven 顶层构建输出（可忽略）                     |
| `*.bat` / `*.sh` / `*.ps1` | 一键启动、停止、升级脚本                         |
| `*.md`                     | 项目文档（快速入门、百炼集成指南、认证指南等）   |

---

## 三、`backend-java/` — Java 后端

基于 **Spring Boot**，采用经典分层架构：`Controller → Service → Repository → Entity`。

主包路径：`com.medlab`

### 3.1 启动入口

| 文件                          | 说明                   |
| ----------------------------- | ---------------------- |
| `MedLabAgentApplication.java` | Spring Boot 应用启动类 |

### 3.2 `agent/` — AI Agent 核心

| 文件                    | 说明                                                     |
| ----------------------- | -------------------------------------------------------- |
| `MedicalAgent.java`     | 医疗 Agent 主体，编排多轮对话与工具调用                  |
| `AgentFuncRealize.java` | Agent 工具函数的具体实现（供模型 function-calling 调用） |

### 3.3 `config/` — 全局配置

| 文件                           | 说明                                               |
| ------------------------------ | -------------------------------------------------- |
| `SecurityConfig.java`          | Spring Security 安全配置（接口鉴权规则、放行路径） |
| `JwtAuthenticationFilter.java` | JWT 认证过滤器，拦截每个请求校验 Token 合法性      |
| `WebConfig.java`               | CORS 跨域配置                                      |
| `RestTemplateConfig.java`      | RestTemplate HTTP 客户端 Bean 配置                 |

### 3.4 `controller/` — API 接口层

接收前端 HTTP 请求，参数校验后委派给 Service 处理。

| 文件                   | 说明                                                                |
| ---------------------- | ------------------------------------------------------------------- |
| `AgentController.java` | 核心业务接口：AI 对话（流式 SSE）、文件上传、病历记录、过敏药物操作 |
| `AuthController.java`  | 认证接口：用户注册、登录、获取当前用户信息                          |

### 3.5 `databases/` — JPA 实体（Entity）

与数据库表一一映射的 Java 实体类。

| 文件                   | 对应表              | 说明                             |
| ---------------------- | ------------------- | -------------------------------- |
| `User.java`            | `users`             | 用户信息（含终身病历、过敏药物） |
| `LabReport.java`       | `lab_reports`       | 检验报告                         |
| `ReportItem.java`      | `report_items`      | 报告检验项明细                   |
| `ChatMessage.java`     | `chat_messages`     | 聊天消息记录                     |
| `KnowledgeRecord.java` | `knowledge_records` | 知识库向量记录（pgvector）       |

### 3.6 `db-managing/` — 数据访问层（Repository）

Spring Data JPA 接口，封装数据库 CRUD 与自定义查询。

| 文件                             | 说明                                       |
| -------------------------------- | ------------------------------------------ |
| `UserRepository.java`            | 用户查询、病历追加（CONCAT）、过敏药物更新 |
| `KnowledgeRecordRepository.java` | 知识库向量相似度检索                       |

### 3.7 `Desensitize-filter/` — DTO 数据传输对象

请求与响应的数据封装，用于接口数据脱敏和格式约束。

| 子目录 / 文件                    | 说明                          |
| -------------------------------- | ----------------------------- |
| `request/LoginRequest.java`      | 登录请求体（身份证号 + 密码） |
| `request/RegisterRequest.java`   | 注册请求体                    |
| `response/ApiResponse.java`      | 统一 API 响应包装             |
| `response/AuthResponse.java`     | 认证响应（含 JWT Token）      |
| `response/UserInfoResponse.java` | 用户信息响应（脱敏后）        |

### 3.8 `service/` — 业务逻辑层

处理核心业务规则，由 Controller 调用，向下调用 Repository。

| 文件                         | 说明                                           |
| ---------------------------- | ---------------------------------------------- |
| `AuthService.java`           | 注册 / 登录验证 / 用户信息查询                 |
| `BailianQianwenService.java` | 阿里云百炼千问大模型调用（流式 SSE 响应）      |
| `KnowledgeService.java`      | 基于 pgvector 的知识库向量检索服务             |
| `StorageService.java`        | 文件上传与本地存储服务                         |
| `UserMedicalService.java`    | 用户病历追加与过敏药物管理（供 AI 上下文参考） |

### 3.9 `tools/` — Agent 工具函数

大模型 function-calling 可调用的外部工具。

| 文件            | 说明                 |
| --------------- | -------------------- |
| `LabTools.java` | 检验报告相关工具函数 |

### 3.10 `util/` — 通用工具类

| 文件                    | 说明                             |
| ----------------------- | -------------------------------- |
| `JwtTokenProvider.java` | JWT Token 生成、解析、有效期验证 |

---

## 四、`frontend-vue/` — Vue 3 前端

基于 **Vue 3 + Pinia + Vue Router + Axios**，构建单页对话界面。

### 4.1 入口

| 文件      | 说明                                        |
| --------- | ------------------------------------------- |
| `main.js` | Vue 应用初始化（挂载路由、Pinia、全局样式） |
| `App.vue` | 根组件，`<router-view>` 出口                |

### 4.2 `components/` — UI 组件

| 文件                 | 说明                                                 |
| -------------------- | ---------------------------------------------------- |
| `ChatWindow.vue`     | 主聊天窗口：消息列表、输入框、文件上传、病历确认弹窗 |
| `ChatMessage.vue`    | 单条消息渲染（区分用户 / AI 角色，支持 Markdown）    |
| `LoadingSpinner.vue` | 通用加载动画                                         |

### 4.3 `views/` — 页面视图

| 文件        | 说明                               |
| ----------- | ---------------------------------- |
| `Login.vue` | 登录 / 注册页面（身份证号 + 密码） |

### 4.4 `stores/` — Pinia 状态管理

| 文件           | 说明                                         |
| -------------- | -------------------------------------------- |
| `authStore.js` | 用户认证状态（Token 存储、登录态恢复、登出） |
| `chatStore.js` | 聊天消息列表状态管理                         |

### 4.5 `services/` — API 通信层

| 文件            | 说明                                                      |
| --------------- | --------------------------------------------------------- |
| `ApiService.js` | Axios 实例封装，统一管理所有后端接口调用（含 JWT 拦截器） |

### 4.6 `router/` — 路由配置

| 文件       | 说明                                          |
| ---------- | --------------------------------------------- |
| `index.js` | 路由定义：`/login`（登录页）、`/`（主聊天页） |

### 4.7 `assets/` — 静态资源

| 文件       | 说明       |
| ---------- | ---------- |
| `main.css` | 全局样式表 |

---

## 五、`ai-services-python/` — Python AI 微服务

### `ocr_service/` — OCR 图片识别服务

| 文件               | 说明                               |
| ------------------ | ---------------------------------- |
| `main.py`          | FastAPI 服务入口，提供 `/ocr` 接口 |
| `requirements.txt` | Python 依赖清单                    |
| `Dockerfile`       | 容器化构建文件                     |

---

## 六、`infrastructure/` — 基础设施

| 文件                 | 说明                                                      |
| -------------------- | --------------------------------------------------------- |
| `docker-compose.yml` | Docker 编排：PostgreSQL（pgvector）、后端、前端、OCR 服务 |
| `init.sql`           | 数据库初始化脚本（建表、建索引、启用扩展）                |
| `.env`               | 环境变量配置（数据库密码、API Key 等）                    |
| `nginx/nginx.conf`   | Nginx 反向代理配置（前端静态资源 + 后端 `/api` 转发）     |

---

## 七、分层架构速查

```
┌─────────────┐
│  前端 (Vue)  │  ← 用户交互、状态管理、API 调用
├─────────────┤
│  Controller  │  ← 接收 HTTP 请求，参数校验，返回响应
├─────────────┤
│   Service    │  ← 业务逻辑：数据拼装、规则校验、外部调用
├─────────────┤
│  Repository  │  ← 数据库操作：CRUD、自定义 JPQL 查询
├─────────────┤
│   Entity     │  ← JPA 实体，与数据库表一一映射
├─────────────┤
│  PostgreSQL  │  ← 数据持久化存储（含 pgvector 向量索引）
└─────────────┘
```

调用方向**自上而下、单向依赖**：`Controller → Service → Repository → Entity`。
