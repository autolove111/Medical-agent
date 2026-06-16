# Medical-agent

医疗检验报告解读智能助手。当前版本采用 Vue 前端、Python FastAPI 主后端、PaddleOCR 独立服务的三服务结构，已支持化验单图片上传、OCR 结构化提取、指标分类、联动分析、RAG/Agent 对话和流式返回。

> 重要：本 README 只描述当前 `Medical-agent` 目录。不要和另一个历史目录 `MedicalAgent` 的 Java/Docker 架构混用。

## 当前状态

- 当前开发分支：`tbz_2`
- 主分支/队友基线：`zly_3`
- 本地推荐运行方式：Conda + 三终端
- Docker 状态：当前仓库只保留 OCR 服务 Dockerfile，尚未为当前三服务架构维护完整 docker-compose
- 环境总文档：[环境配置与部署说明.md](环境配置与部署说明.md)

## 核心能力

- 化验单图片上传与 PaddleOCR 本地识别
- 支持 Windows 中文路径场景，上传后会转存到 ASCII 临时路径供 OCR 使用
- 双栏化验单表格解析，提取指标名、数值、单位、参考范围
- 40+ 检验指标参考范围匹配，支持年龄/性别分层与危急值检测
- 多指标联动分析，例如肾功能、肝功能、感染、电解质等
- 基于本地 HuggingFace 模型的自研 Agent 调度
- RAG 检索、短期/长期记忆、来源追踪、输出安全过滤
- Vue 3 前端展示聊天、报告上传、指标面板和来源引用

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite + Pinia + Axios |
| 主后端 | FastAPI + Uvicorn + SQLAlchemy |
| OCR | PaddleOCR / PaddlePaddle |
| LLM | 本地 HuggingFace Transformers 模型，默认 Qwen2.5 |
| RAG | sentence-transformers + FAISS |
| 数据库 | 本地 SQLite，服务器推荐 PostgreSQL |
| 缓存/短期记忆 | Redis，可选增强 |
| 环境管理 | Conda，Python 3.11 |

## 项目结构

```text
Medical-agent/
├── frontend-vue/                         # Vue 前端，默认 :8888
├── python_service/                       # FastAPI 主后端，默认 :8000
│   ├── server.py                         # 服务入口
│   ├── core/config.py                    # 配置读取
│   ├── api/routes/                       # auth/chat/report/user 路由
│   ├── app/business/                     # 报告管线、指标分类、联动分析、解读引擎
│   ├── app/persistence/                  # SQLite/PostgreSQL 持久化
│   ├── harness/                          # 自研 Agent/LLM/Memory 框架
│   └── service/rag/                      # RAG 检索
├── ai-services-python/ocr_service/       # PaddleOCR 服务，默认 :8001
│   ├── paddle_server.py                  # OCR FastAPI 入口
│   ├── paddle_ocr.py                     # OCR 识别与表格解析
│   ├── main.py                           # 旧 DashScope OCR 兼容入口
│   └── Dockerfile                        # OCR 服务容器化文件
├── docs/                                 # 技术文档
├── test/                                 # 阶段验证脚本
├── test_png/                             # 本地样例图片
├── 环境配置与部署说明.md                   # 环境、启动、部署主文档
└── README.md
```

## 环境说明

完整说明见 [环境配置与部署说明.md](环境配置与部署说明.md)。

简要原则：

- `zly_3` 默认环境名多见于 `medlab-langchain`、`medlab-ocr`。
- 你本地使用 `medagent` 没问题，环境名不影响代码。
- 单环境开发更省事，双环境开发更干净。
- 主后端真正读取 `python_service/.env`。
- 根目录 `.env` 目前仅作为历史/全局兼容配置，不是当前主后端的主要配置入口。

## 快速启动

### 1. 安装依赖

单环境示例：

```powershell
conda create -n medagent python=3.11 -y
conda activate medagent

cd E:\开源项目\Medical-agent\python_service
conda env update -n medagent -f environment.yml

cd E:\开源项目\Medical-agent\ai-services-python\ocr_service
pip install -r requirements.txt

cd E:\开源项目\Medical-agent\frontend-vue
npm install
```

双环境也可行：

```powershell
cd E:\开源项目\Medical-agent\python_service
conda env create -f environment.yml

cd E:\开源项目\Medical-agent\ai-services-python\ocr_service
conda env create -f environment.yml
```

### 2. 配置 `python_service/.env`

本地最小配置：

```env
RAG_USE_LOCAL_EMBEDDING=true
LLM_MODEL_PATH=./models/Qwen2.5-7B-Instruct
RAG_LOCAL_EMBEDDING_PATH=./models/bce-embedding-base_v1
VECTOR_DB_PATH=./harness/memory/knowledge/data/vector_db

DATABASE_URL=postgresql://medlab_user:medlab_password@localhost:5432/medlab_db
REDIS_HOST=localhost
REDIS_PORT=6379

OCR_SERVICE_URL=http://localhost:8001
OCR_SERVICE_TIMEOUT=180
OCR_ALLOW_MOCK_FALLBACK=false
```

本地没装 PostgreSQL 时，当前代码可降级 SQLite。Redis 不可用时缓存/短期记忆能力会降级，但 OCR 上传主链路不应被阻断。

### 3. 启动服务

终端 1：Python 后端

```powershell
conda activate medagent
cd E:\开源项目\Medical-agent\python_service
python server.py
```

终端 2：PaddleOCR

```powershell
conda activate medagent
cd E:\开源项目\Medical-agent\ai-services-python\ocr_service
python paddle_server.py
```

终端 3：前端

```powershell
cd E:\开源项目\Medical-agent\frontend-vue
npm run dev
```

访问：

```text
前端: http://localhost:8888
主后端: http://localhost:8000/docs
OCR: http://localhost:8001/api/v1/health
```

## 验证

预热 OCR：

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/health
Invoke-RestMethod http://localhost:8001/api/v1/ready
```

直测主后端上传：

```powershell
curl.exe -F "file=@E:\Temp\medagent_ocr\sample.jpg" `
  -F "user_id=default" `
  -F "age=0" `
  -F "gender=" `
  http://localhost:8000/api/report/upload
```

返回 JSON 中：

- `ocr_mock` 应为 `false`
- `indicators` 为结构化指标列表
- `raw_ocr_text` 为 OCR 原始提取文本

阶段脚本：

```powershell
conda activate medagent
cd E:\开源项目\Medical-agent
python test/verify_all_phases.py
```

## API 摘要

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 主后端健康检查 |
| `POST` | `/api/v1/auth/register` | 用户注册 |
| `POST` | `/api/v1/auth/login` | 用户登录 |
| `POST` | `/api/report/upload` | 上传化验单并触发 OCR/结构化 |
| `GET` | `/api/report/{report_id}` | 查看报告详情 |
| `POST` | `/api/chat` | 同步聊天 |
| `GET` | `/api/chat/stream` | SSE 流式聊天 |
| `GET` | `/api/chat/sources` | 来源引用 |
| `GET` | `/api/user/profile` | 用户画像 |
| `PUT` | `/api/user/profile` | 更新用户画像 |
| `POST` | `/api/user/reset` | 重置会话 |

OCR 服务：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | OCR 依赖和进程状态 |
| `GET` | `/api/v1/ready` | 加载 PaddleOCR 模型并检查可用性 |
| `POST` | `/api/v1/analyze-vision` | 识别本地图片路径 |

## 本地与服务器路线

本地阶段：

- 优先跑通 OCR、上传、结构化和前端。
- LLM 可以用较小模型或暂不触发。
- SQLite 和 Redis 降级可以接受。

服务器阶段：

- PostgreSQL + Redis 固定化。
- 模型权重放在服务器磁盘，例如 `/data/medical-agent/models`。
- `LLM_MODEL_PATH` 指向服务器模型目录。
- Python 后端和 OCR 服务拆开部署。
- 前端构建后用 Nginx 或静态服务托管。

如果后续希望使用 vLLM、TGI、Ollama 或 OpenAI-compatible 模型服务，需要新增远程 LLM 适配层。当前代码默认是本地 HuggingFace 模型加载，不会只靠改 `.env` 自动切到远程推理服务。

## 常见问题

### OCR health 正常但上传失败

检查 OCR 是否真的加载模型：

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/ready
```

如果 OCR 直连正常但 `/api/report/upload` 失败，看主后端日志中的 `api.routes.report` 和 `app.business.report_pipeline`。

### 中文路径导致文件不存在

Windows PowerShell 手动 POST 中文路径时可能出现编码问题。当前代码已经在主后端和 OCR 服务端做 ASCII 临时路径保护；手动测试建议仍使用 `E:\Temp\medagent_ocr\sample.jpg` 这种 ASCII 路径。

### 返回内置 Mock 数据

确认：

```env
OCR_ALLOW_MOCK_FALLBACK=false
```

正式验收时不要打开 Mock 回退。

### 显存不足

```powershell
nvidia-smi
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
```

本地显存不足时，先验证 OCR 和报告管线，LLM 切小模型或放到服务器上。

