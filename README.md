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
Medical-agent/
├── python_service/                       # 核心 Python AI 服务
│   ├── server.py                         # FastAPI 应用入口 (Phase 1)
│   ├── core/
│   │   └── config.py                     # Pydantic 全局配置
│   ├── api/                              # API 路由层 (Phase 1-4)
│   │   ├── models.py                     # Pydantic 请求/响应模型
│   │   ├── dependencies.py               # AgentPool 会话池 + 工具注册
│   │   └── routes/
│   │       ├── auth.py                   # 注册/登录/Token 验证 (兼容旧前端)
│   │       ├── chat.py                   # 同步+SSE 流式对话 (Phase 1-3)
│   │       ├── report.py                 # 报告上传+OCR+管线 (Phase 2)
│   │       └── user.py                   # 用户画像 CRUD (Phase 4)
│   ├── app/                              # 业务逻辑层 (Phase 2-6)
│   │   ├── business/
│   │   │   ├── lab_report.py             # LabReport/LabIndicator 数据模型
│   │   │   ├── indicator_classifier.py   # 40+ 参考范围分类器 (年龄/性别分层)
│   │   │   ├── correlation_engine.py     # 15 组多指标联动规则引擎
│   │   │   ├── report_pipeline.py        # OCR→结构化→分类→联动 完整管线
│   │   │   ├── interpretation_engine.py  # 6 段式解读 Prompt 组装
│   │   │   ├── source_tracker.py         # 知识库来源引用追踪
│   │   │   └── dietary_advisor.py        # 10+ 类指标饮食运动建议
│   │   ├── safety/
│   │   │   └── output_guard.py           # OutputGuard 安全红线 (Phase 6)
│   │   └── persistence/                  # 持久化层 (Phase 4)
│   │       ├── database.py               # SQLite 引擎 + 会话工厂
│   │       ├── models.py                 # User/Report/Chat ORM 模型
│   │       └── repositories/
│   │           ├── user_repo.py          # 用户 CRUD
│   │           ├── report_repo.py        # 报告 CRUD
│   │           └── chat_repo.py          # 对话记录 CRUD
│   ├── harness/                          # 自研 Harness 框架层
│   │   ├── llm_core/
│   │   │   └── model_loader.py           # 模型加载器（单例 + 懒加载 + 4-bit）
│   │   ├── llm_adapter/
│   │   │   ├── chat_model.py             # 推理适配器 (invoke/stream + 截断)
│   │   │   ├── create_agent.py           # Agent 工厂 + LabAgent
│   │   │   ├── agent_loop.py             # AgentLoop 调度循环 (Phase 5)
│   │   │   ├── tool_parser.py            # 工具调用解析 (XML+Action+JSON)
│   │   │   └── agent_tools.py            # 4 个医疗专用工具
│   │   ├── state/
│   │   │   └── agent_state.py            # Agent 状态管理 (消息/快照/回滚)
│   │   ├── prompt/
│   │   │   └── prompt_context.py         # 四层提示词组装引擎
│   │   └── long_memory/knowledge/        # RAG 长期记忆系统
│   │       ├── rag.py                    # RAG 系统总入口（单例）
│   │       ├── rag_formatter.py          # 检索结果格式化 + 来源元数据提取
│   │       ├── hybrid_retriever.py       # 混合检索（关键词+语义+重排序）
│   │       ├── query_rewriter.py         # 医学查询改写器 (60+ 缩写)
│   │       ├── embedding_FAISS.py        # BCE 嵌入 + FAISS 向量库
│   │       ├── reference_ranges.py       # 40+ 种检验指标参考范围
│   │       └── ...                       # 分块策略/文档加载/文本清洗
│   ├── models/                           # 本地模型权重（需自行下载）
│   │   ├── Qwen2.5-7B-Instruct/
│   │   └── bce-embedding-base_v1/
│   └── data/                             # SQLite 数据库文件
├── ai-services-python/ocr_service/       # OCR 服务
│   ├── main.py                           # 原 DashScope OCR (云 API, 兼容)
│   ├── paddle_ocr.py                     # PaddleOCR 引擎 (本地, Phase 7)
│   └── paddle_server.py                  # PaddleOCR FastAPI 入口 (:8001)
├── frontend-vue/                         # Vue 3 前端
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
├── test/                                 # 测试脚本
│   ├── 终端多轮对话测试.py                # 交互式多轮对话
│   ├── create_modle_test.py              # 模型加载单元测试
│   ├── 验证RAG.py                        # RAG 有效性验证
│   ├── 验证检索引擎优化.py                # 检索引擎验证
│   ├── verify_phase1.py                  # Phase 1: FastAPI 服务层
│   ├── verify_phase2.py                  # Phase 2: 报告处理管线
│   ├── verify_phase3.py                  # Phase 3: 解读引擎+来源引用
│   ├── verify_phase4_5.py                # Phase 4+5: 持久化+AgentLoop
│   ├── verify_phase6.py                  # Phase 6: 安全红线框架
│   └── verify_all_phases.py              # 一键全量验证
├── picture/                              # 测试用化验单样例
├── 大创文档.md                            # 技术架构设计文档
└── README.md                             # 本文件
```

## 快速开始

### 环境要求

- NVIDIA 显卡（≥6GB 显存，推荐 8GB+）或 CPU（推理较慢）
- CUDA 12.4+、Python 3.11、Conda
- Node.js 18+（仅前端）

### 1. 创建环境并安装依赖

项目使用 conda environment.yml 管理依赖，一条命令即可复现环境。

```powershell
# Python 后端环境 (medlab-langchain)
cd Medical-agent/python_service
conda env create -f environment.yml

# OCR 服务环境 (medlab-ocr)
cd Medical-agent/ai-services-python/ocr_service
conda env create -f environment.yml

# 前端依赖
cd Medical-agent/frontend-vue
npm install
```

如果已有环境，只更新新增依赖：

```powershell
conda activate medlab-langchain
pip install sqlalchemy python-multipart langchain-community langchain-core langchain-text-splitters

conda activate medlab-ocr
pip install paddlepaddle==2.6.2 paddleocr==2.8.1
```

### 2. 下载模型权重

```powershell
# Qwen2.5-7B-Instruct (主模型, ~14GB)
python -c "from modelscope import snapshot_download; snapshot_download('qwen/Qwen2.5-7B-Instruct', cache_dir='python_service/models/Qwen2.5-7B-Instruct')"

# bce-embedding-base_v1 (嵌入模型, ~1GB)
python -c "from huggingface_hub import snapshot_download; snapshot_download('maidalun1020/bce-embedding-base_v1', local_dir='python_service/models/bce-embedding-base_v1')"
```

### 3. 配置环境变量

编辑 `python_service/.env`：

```env
RAG_USE_LOCAL_EMBEDDING=true
LLM_MODEL_PATH=./models/Qwen2.5-7B-Instruct
RAG_LOCAL_EMBEDDING_PATH=./models/bce-embedding-base_v1
VECTOR_DB_PATH=./harness/long_memory/knowledge/vector_db
```

### 4. 启动服务（三终端）

```powershell
# 终端 1: Python 后端
conda activate medlab-langchain
cd python_service
python server.py
# → http://localhost:8000 (Swagger: /docs)

# 终端 2: PaddleOCR 服务
conda activate medlab-ocr
cd ai-services-python/ocr_service
python paddle_server.py
# → http://localhost:8001 (首次启动自动下载 PP-OCRv4 模型 ~80MB)

# 终端 3: 前端
cd frontend-vue
npm install
npm run dev
# → http://localhost:8888
```

### 5. 验证

```powershell
conda activate medagent
cd Medical-agent

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
| `harness/llm_adapter/create_agent.py` | +`_safety_check()` + `agent_loop()` | 安全检测 + 多步推理 |
| `harness/llm_adapter/chat_model.py` | +话题标签截断 + 流式停止检测 | 抑制小模型幻觉 |
| `harness/long_memory/knowledge/rag_formatter.py` | +`extract_source_metadata()` | 结构化来源输出 |
| `ai-services-python/ocr_service/main.py` | REDIS_HOST 支持环境变量 + 本地文件读取 | 本地开发兼容 |
| `frontend-vue/vite.config.js` | 代理指向 :8000 + 新增 /v1 代理 | 对接新后端 |
| `frontend-vue/src/App.vue` | 移除不存在的 intro.mp4 | 修复启动报错 |
| `frontend-vue/src/services/ApiService.js` | 新增 10 个 API 方法 + 修复双 /api | 对接新后端 |
| `frontend-vue/src/components/ChatWindow.vue` | 集成指标面板 + 上传组件 + 来源引用 | 业务页面 |

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
