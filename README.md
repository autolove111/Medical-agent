# Medical-agent — 医疗检验助手智能体

大创项目：基于自研 Harness 架构的医疗检验报告解读智能助手。

## 项目简介

Medical-agent 是一个面向医疗检验场景的智能对话系统，能够解读化验报告、分析检验指标异常原因、给出专业医学建议。项目的核心特点是**渐进式自主研发**——从模型加载、推理调度、状态管理到提示词组装，全部自研实现，不依赖 LangChain/LangGraph 等开源框架（RAG 检索层除外，待后续去框架化）。

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 大语言模型 | Qwen2.5-7B-Instruct（4-bit 量化，本地部署） |
| 嵌入模型 | bce-embedding-base_v1（768 维，RAG 检索） |
| OCR 引擎 | PaddleOCR (PP-OCRv4)（本地部署，离线可用） |
| 向量数据库 | FAISS（CPU 运行） |
| 推理框架 | PyTorch 2.6 + Transformers + bitsandbytes |
| API 服务 | FastAPI + Uvicorn + SSE 流式 |
| 数据库 | SQLite + SQLAlchemy ORM |
| 前端 | Vue 3 + Vite + Pinia + Axios |
| 环境管理 | Conda (medagent, Python 3.11) |

## Demo 全流程架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3 :8888)                       │
│  Login → ChatWindow → ReportUpload → IndicatorPanel → Sources  │
│                         DisclaimerBar                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │  /api/*   /api/v1/auth/*
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Python FastAPI 后端 (:8000)                     │
│                                                                 │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │ Auth 模块 │  │ Report 管线   │  │ Chat 管线                  │  │
│  │ register  │  │ upload → OCR  │  │ input → RAG → LLM → guard │  │
│  │ login     │  │ → classify   │  │   → SSE stream → response │  │
│  │ token验   │  │ → correlate  │  │                            │  │
│  └────┬─────┘  └──────┬───────┘  └────────────┬───────────────┘  │
│       │               │                        │                  │
│       ▼               ▼                        ▼                  │
│  ┌─────────┐  ┌──────────────┐  ┌────────────────────────────┐  │
│  │ SQLite  │  │ PaddleOCR    │  │ LabAgent                    │  │
│  │ users   │  │ :8001 本地OCR│  │ ├─ AgentState (快照/回滚)    │  │
│  │ reports │  │ 28行全量提取  │  │ ├─ RAG (bce-embedding)     │  │
│  │ chat    │  │ 表格+正则解析  │  │ ├─ AgentLoop (max 5 steps) │  │
│  └─────────┘  └──────┬───────┘  │ ├─ tool_parser (4 tools)   │  │
│                      │           │ ├─ OutputGuard (安全红线)   │  │
│                      ▼           │ └─ Qwen 7B 推理             │  │
│              化验单图片 → 文本    └────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 解读引擎 (InterpretationEngine)                           │   │
│  │ ├─ 40+ 参考范围匹配 (年龄/性别分层)                        │   │
│  │ ├─ 15 组多指标联动规则                                    │   │
│  │ ├─ 10+ 类指标饮食运动建议                                  │   │
│  │ └─ SourceTracker 来源引用追踪                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 完整交互链路

```
用户上传化验单图片
  │
  ├─→ PaddleOCR 本地识别 → 28 个文本块全量提取
  │     ├─ 表格布局：按 Y/X 坐标分行分列 → 提取 指标名/数值/单位/参考范围
  │     ├─ 自由文本：逐行正则解析 → 含已知指标关键词的行
  │     └─ 无法解析：原始文本全量保留，由 LLM 直接理解
  │
  ├─→ 指标分类 (40+ 参考范围)
  │     └─ 年龄 7 段分层 (infant→elderly) + 性别差异 + 危急值检测
  │
  ├─→ 联动分析 (15 组规则)
  │     └─ 肾功能受损 / 肝细胞损伤 / 代谢综合征 / 贫血 / 感染 / 电解质...
  │
  ├─→ 饮食运动建议 (10+ 类指标)
  │     └─ 循证规则 → 饮食/运动分类 → 来源标注
  │
  ├─→ 解读 Prompt 组装 (6 段式)
  │     └─ 总览 → 逐项解读 → 关联分析 → 健康建议 → 参考来源 → 免责声明
  │
  ├─→ LabAgent.chat()
  │     ├─ RAG 检索 (bce-embedding → FAISS → 混合检索)
  │     ├─ Qwen 7B 推理 (4-bit 量化)
  │     ├─ _truncate_at_role_marker (截断幻觉续写)
  │     └─ _safety_check → OutputGuard.sanitize() + 免责声明注入
  │
  └─→ SSE 流式返回前端
        ├─ ChatMessage 逐 token 渲染
        ├─ IndicatorPanel 指标总览 (危急/异常/正常分组)
        ├─ Sources Panel 参考来源展开
        └─ DisclaimerBar 底部固定免责声明
```

## 项目结构

```
dachuang/
├── frontend/                         # Vue 3 前端
│   └── src/
│       ├── components/
│       │   ├── ChatWindow.vue            # 主聊天窗口 (侧栏+来源面板)
│       │   ├── ChatMessage.vue           # Markdown 消息渲染
│       │   ├── IndicatorCard.vue         # 单项指标卡片 (5 状态颜色)
│       │   ├── IndicatorPanel.vue        # 指标总览面板 (分组折叠)
│       │   ├── ReportUpload.vue          # 上传对话框 (拖拽+预览)
│       │   └── DisclaimerBar.vue         # 底部固定免责声明
│       ├── views/Login.vue               # 登录/注册页
│       ├── stores/                       # Pinia 状态 (auth/chat)
│       ├── services/ApiService.js        # API 封装 (新旧兼容)
│       └── router/index.js               # 路由 + 认证守卫
│
├── backend/                          # 后端服务 (FastAPI :8000)
│   ├── server.py                         # FastAPI 应用入口
│   ├── app/
│   │   ├── api/                          # API 路由层
│   │   │   ├── models.py                 # Pydantic 请求/响应模型
│   │   │   └── routes/
│   │   │       ├── auth.py               # 注册/登录/Token 验证
│   │   │       ├── chat.py               # 同步+SSE 流式对话
│   │   │       └── report.py             # 报告上传+OCR+管线
│   │   ├── core/                         # 核心配置
│   │   │   ├── config.py                 # Pydantic 全局配置
│   │   │   └── logging.py                # 日志配置
│   │   ├── models/                       # 数据模型
│   │   │   ├── database.py               # 数据库引擎 + 会话工厂
│   │   │   └── reference_ranges.py       # 40+ 种检验指标参考范围
│   │   └── services/                     # 业务服务层
│   │       ├── lab_report.py             # LabReport/LabIndicator 数据模型
│   │       ├── indicator_classifier.py   # 40+ 参考范围分类器 (年龄/性别分层)
│   │       ├── correlation_engine.py     # 15 组多指标联动规则引擎
│   │       ├── report_pipeline.py        # OCR→结构化→分类→联动 完整管线
│   │       ├── interpretation_engine.py  # 6 段式解读 Prompt 组装
│   │       ├── source_tracker.py         # 知识库来源引用追踪
│   │       ├── dietary_advisor.py        # 10+ 类指标饮食运动建议
│   │       └── output_guard.py           # OutputGuard 安全红线
│
├── ai-services/                      # AI 服务 (FastAPI :8001)
│   ├── server.py                         # AI 服务入口
│   ├── llm/                              # LLM 服务
│   │   ├── chat_model.py                 # 推理适配器 (invoke/stream + 截断)
│   │   ├── create_agent.py               # Agent 工厂 + LabAgent
│   │   └── model_loader.py               # 模型加载器（单例 + 懒加载 + 4-bit）
│   ├── rag/                              # RAG 检索增强生成服务
│   │   ├── rag.py                        # RAG 系统总入口（单例）
│   │   ├── rag_formatter.py              # 检索结果格式化 + 来源元数据提取
│   │   ├── hybrid_retriever.py           # 混合检索（关键词+语义+重排序）
│   │   ├── query_rewriter.py             # 医学查询改写器 (60+ 缩写)
│   │   ├── embedding.py                  # BCE 嵌入 + FAISS 向量库
│   │   └── ...                           # 分块策略/文档加载/文本清洗
│   ├── memory/                           # 统一记忆系统
│   │   ├── short_memory/                 # 短期记忆
│   │   ├── long_term/                    # 长期记忆（用户画像/事件记录/快照）
│   │   ├── persistence/                  # 持久化层
│   │   └── knowledge/                    # 医学知识数据层
│   ├── tools/                            # 工具系统
│   │   ├── tool_registry.py              # 工具注册表
│   │   └── tools/                        # 4 个医疗专用工具
│   ├── ocr/                              # OCR 服务
│   │   ├── main.py                       # 原 DashScope OCR (云 API, 兼容)
│   │   ├── paddle_ocr.py                 # PaddleOCR 引擎 (本地)
│   │   └── paddle_server.py              # PaddleOCR FastAPI 入口
│   └── loop/                             # Agent 循环框架
│       ├── agentic_loop/                 # ReAct 多步推理循环
│       ├── context_window/               # 上下文窗口控制
│       └── prompt/                       # 提示词组装引擎
│
├── models/                           # 本地模型权重（需自行下载）
│   ├── Qwen2.5-7B-Instruct/
│   ├── Zhinao-ChineseModernBert-Embedding/
│   └── bge-reranker-base/
│
├── test/                                 # 测试脚本
├── picture/                              # 测试用化验单样例
├── 大创文档.md                            # 技术架构设计文档
└── README.md                             # 本文件
```

## 快速开始

### 环境要求

- NVIDIA 显卡（≥6GB 显存，推荐 8GB+）或 CPU（推理较慢）
- CUDA 12.4+、Python 3.11、Conda
- Node.js 18+（仅前端）
- Redis（消息队列 + 短期记忆）

### 1. 创建环境并安装依赖

```powershell
conda create -n medagent python=3.11 -y
conda activate medagent

# PyTorch (CUDA 12.4)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 核心依赖
pip install transformers accelerate bitsandbytes sentencepiece
pip install fastapi uvicorn pydantic pydantic-settings python-dotenv
pip install sentence-transformers faiss-cpu
pip install redis httpx requests tenacity tiktoken aiofiles sqlalchemy python-multipart

# RAG 检索层
pip install langchain-community langchain-core langchain-text-splitters

# PaddleOCR 本地 OCR (Phase 7)
pip install paddlepaddle==2.6.2 paddleocr==2.8.1

# 前端依赖
cd frontend && npm install && cd ..
```

### 2. 下载模型权重

```powershell
# Qwen2.5-7B-Instruct (主模型, ~14GB)
python -c "from modelscope import snapshot_download; snapshot_download('qwen/Qwen2.5-7B-Instruct', cache_dir='models/Qwen2.5-7B-Instruct')"

# Zhinao-ChineseModernBert-Embedding (嵌入模型)
python -c "from modelscope import snapshot_download; snapshot_download('Zhinao/ChineseModernBert-Embedding', cache_dir='models/Zhinao-ChineseModernBert-Embedding')"

# bge-reranker-base (重排序模型)
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-reranker-base', cache_dir='models/bge-reranker-base')"
```

### 3. 配置环境变量

编辑 `.env`：

```env
# 模型路径
LLM_MODEL_PATH=E:\xiangmu\dachuang\models\Qwen2.5-7B-Instruct
EMBEDDING_MODEL_PATH=E:\xiangmu\dachuang\models\Zhinao-ChineseModernBert-Embedding
RERANKER_MODEL_PATH=E:\xiangmu\dachuang\models\bge-reranker-base

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# 服务地址
OCR_SERVICE_URL=http://localhost:8001
BACKEND_URL=http://localhost:8000
```

### 4. 启动服务

需要 **6 个终端窗口**，按顺序启动：

```powershell
# ===== 终端 1：Redis（必须先启动）=====
# Windows: 双击 redis-server.exe 或
redis-server

# ===== 终端 2：后端 FastAPI 服务（:8000）=====
conda activate medagent
cd backend
python server.py
# → http://localhost:8000/docs (Swagger UI)

# ===== 终端 3：Loop Worker（任务调度器）=====
conda activate medagent
cd backend
python -m app.worker.loop_worker
# 消费 Redis 任务队列，分发给 LLM/RAG/OCR

# ===== 终端 4：LLM Worker（大模型推理）=====
conda activate medagent
cd backend
python -m app.worker.llm_worker
# 加载 Qwen2.5-7B 模型，首次启动约 30 秒

# ===== 终端 5：RAG Worker（知识检索）=====
conda activate medagent
cd backend
python -m app.worker.rag_worker
# 加载 SentenceTransformer + CrossEncoder，首次约 25 秒

# ===== 终端 6：前端（:8888）=====
cd frontend
npm run dev
# → http://localhost:8888
```

> **OCR Worker**（可选）：如需本地 OCR 识别化验单，另开终端运行：
> ```powershell
> conda activate medagent
> cd backend
> python -m app.worker.ocr_worker
> ```

### 5. 启动顺序说明

```
Redis → FastAPI 服务 → Worker 进程 → 前端
```

| 服务 | 端口 | 说明 |
|------|------|------|
| Redis | 6379 | 消息队列 + 短期记忆存储 |
| FastAPI 服务 | 8000 | API 网关 + WebSocket 推送 |
| Loop Worker | — | 任务调度：ReAct（对话）/ Plan（报告） |
| LLM Worker | — | Qwen2.5-7B 推理，消费 `medlab:list:llm` 队列 |
| RAG Worker | — | 知识检索，消费 `medlab:list:rag` 队列 |
| OCR Worker | — | PaddleOCR 识别，消费 `medlab:list:ocr` 队列 |
| 前端 | 8888 | Vue 3 开发服务器 |

### Worker 架构

```
前端 WebSocket
     │
     ▼
FastAPI 服务 (:8000) ── submit_task ──→ Redis 队列
                                            │
                                            ▼
                                     Loop Worker（调度器）
                                      ├─ chat  → ReAct 循环（think→act→observe）
                                      └─ report → Plan 循环（plan→execute→synthesize）
                                           │
                              ┌─────────────┼─────────────┐
                              ▼             ▼             ▼
                         LLM Worker    RAG Worker    OCR Worker
                         (模型推理)    (知识检索)    (OCR识别)
                              │             │             │
                              └─────────────┼─────────────┘
                                            ▼
                                     Redis Pub/Sub
                                            │
                                            ▼
                                     WebSocket 推送 → 前端
```

### 6. 验证

```powershell
conda activate medagent

# 一键验证所有模块 (无需 GPU/模型)
python test/verify_all_phases.py

# 单独验证
python test/verify_phase1.py        # FastAPI 服务层
python test/verify_phase2.py        # 报告管线
python test/verify_phase3.py        # 解读引擎
python test/verify_phase4_5.py      # 持久化 + AgentLoop
python test/verify_phase6.py        # 安全红线

# 原始终端对话测试 (需 GPU + 模型)
python test/终端多轮对话测试.py
```

### 7. 常见问题

**Q: 启动后页面一直转圈？**
A: 检查 Redis 是否运行、AI 服务是否启动完成（模型加载需要时间）。

**Q: RAG 响应很慢？**
A: 首次调用需要加载 SentenceTransformer 和 CrossEncoder 模型，约 25-35 秒。后续调用会很快（1-2 秒）。

**Q: 如何清空所有数据重新开始？**
A: 启动 redis-cli 执行 `FLUSHALL`，然后刷新前端页面。

## 核心架构

### 四层提示词组装

```
Layer 1: System Base Prompt     ← 身份定义 + 全局规则 + 用户画像
Layer 2: Task Instruction       ← 当前任务指令（task_queue）
Layer 3: Context                ← 历史对话 + RAG 检索结果
Layer 4: Format / FewShot       ← 输出格式约束
     ↓
Assistant:                      ← 生成触发标记
```

### 三层记忆架构

```
瞬时记忆 → AgentState.messages  → 当前对话完整消息列表
短期记忆 → task_queue / reasoning_process → 任务追踪
长期记忆 → RAG 知识检索 → FAISS 向量库 + 40+ 指标参考范围
```

### AgentLoop 调度流程 (Phase 5)

```
用户输入 → State(HumanMessage)
  → assemble_final_prompt(state) + 工具描述
  → chat_model.invoke(prompt)
  → parse_tool_call(reply)
    ├─ 有工具调用 → 执行工具 → ToolMessage 写回 state → 循环
    └─ 无工具调用 → 最终回复 → 返回
  max_steps=5 | 快照回滚 | loop detection
```

### OutputGuard 安全管道 (Phase 6)

```
模型输出 → sanitize()
  ├─ BLOCK 规则 (禁止确诊/处方) → 替换为安全回复
  ├─ WARN 规则 (话题标签截断) → 自动裁剪
  └─ LOG 规则 → 仅记录
  → inject_disclaimer() → 返回
```

---

## 开发阶段总览

| Phase | 模块 | 核心文件 | 状态 |
|-------|------|---------|------|
| 基础 | 模型推理 + 状态 + 提示词 + RAG | `harness/` | ✅ |
| 1 | FastAPI 服务层 (6 端点 + SSE) | `server.py`, `api/` | ✅ |
| 2 | 报告管线 (OCR→分类→联动) | `app/business/` | ✅ |
| 3 | 解读引擎 + 来源引用 + 饮食建议 | `interpretation_engine.py` | ✅ |
| 4 | SQLite 持久化 (3 表 + Repository) | `app/persistence/` | ✅ |
| 5 | AgentLoop + 4 医疗工具 | `agent_loop.py`, `agent_tools.py` | ✅ |
| 6 | OutputGuard 安全红线框架 | `app/safety/` | ✅ |
| 7 | PaddleOCR 本地 OCR + 前端组件 | `paddle_ocr.py`, `components/` | ✅ |

### 修改的原始文件

| 文件 | 改动 | 影响 |
|------|------|------|
| `ai-services/llm/create_agent.py` | +`_safety_check()` + `agent_loop()` | 安全检测 + 多步推理 |
| `ai-services/llm/chat_model.py` | +话题标签截断 + 流式停止检测 | 抑制小模型幻觉 |
| `ai-services/rag/rag_formatter.py` | +`extract_source_metadata()` | 结构化来源输出 |
| `ai-services/ocr/main.py` | REDIS_HOST 支持环境变量 + 本地文件读取 | 本地开发兼容 |
| `frontend/vite.config.js` | 代理指向 :8000 + 新增 /v1 代理 | 对接新后端 |
| `frontend/src/App.vue` | 移除不存在的 intro.mp4 | 修复启动报错 |
| `frontend/src/services/ApiService.js` | 新增 10 个 API 方法 + 修复双 /api | 对接新后端 |
| `frontend/src/components/ChatWindow.vue` | 集成指标面板 + 上传组件 + 来源引用 | 业务页面 |

## 分支说明

| 分支 | 说明 |
|------|------|
| `zly_3` | 原始分支，项目初始状态 |
| `tbz_1` | 当前分支，包含 Phase 1-7 全部开发 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/auth/register` | 用户注册 |
| `POST` | `/api/v1/auth/login` | 用户登录 |
| `GET` | `/api/v1/auth/me` | Token 验证 |
| `POST` | `/api/chat` | 同步对话 |
| `GET` | `/api/chat/stream` | SSE 流式对话 |
| `GET` | `/api/chat/sources` | 来源引用查询 |
| `POST` | `/api/report/upload` | 化验单上传+OCR |
| `GET` | `/api/report/{id}` | 报告详情 |
| `GET` | `/api/report/user/{id}/list` | 用户报告列表 |
| `GET` | `/api/user/profile` | 获取用户画像 |
| `PUT` | `/api/user/profile` | 更新用户画像 |
| `POST` | `/api/user/reset` | 重置对话 |
| `GET` | `/api/user/health` | 健康检查 |

## Agent 工具

| 工具名 | 功能 |
|--------|------|
| `reference_lookup` | 查询 40+ 指标参考范围 |
| `calculate_egfr` | CKD-EPI 公式计算 eGFR + 分期 |
| `search_knowledge` | 触发 RAG 医学知识检索 |
| `analyze_indicator` | 单指标异常判定 + 临床意义 |
