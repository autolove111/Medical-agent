# Medical-agent — 医疗检验助手智能体

大创项目：基于自研 Harness 架构的医疗检验报告解读智能助手。

## 项目简介

Medical-agent 是一个面向医疗检验场景的智能对话系统，能够解读化验报告、分析检验指标异常原因、给出专业医学建议。项目的核心特点是**渐进式自主研发**——从模型加载、推理调度、状态管理到提示词组装，全部自研实现，不依赖 LangChain/LangGraph 等开源框架（RAG 检索层除外，待后续去框架化）。

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 大语言模型 | Qwen2.5-7B-Instruct（4-bit 量化，本地部署） |
| 嵌入模型 | bce-embedding-base_v1（768 维，RAG 检索） |
| 向量数据库 | FAISS（CPU 运行） |
| 推理框架 | PyTorch 2.6 + Transformers + bitsandbytes |
| 前端 | Vue 3 + Vite + Pinia + Axios |
| 环境管理 | Conda (medagent, Python 3.11) |

## 项目结构

```
Medical-agent/
├── python_service/                    # 核心 Python AI 服务
│   ├── core/
│   │   └── config.py                  # Pydantic 全局配置
│   ├── harness/                       # 自研 Harness 框架层
│   │   ├── llm_core/
│   │   │   └── model_loader.py        # 模型加载器（单例 + 懒加载 + 4-bit 量化）
│   │   ├── llm_adapter/
│   │   │   ├── chat_model.py          # 推理适配器（invoke/stream，零框架依赖）
│   │   │   └── create_agent.py        # Agent 工厂 + LabAgent + RAG 接入
│   │   ├── state/
│   │   │   └── agent_state.py         # Agent 状态管理（消息/快照/回滚/记忆）
│   │   ├── prompt/
│   │   │   └── prompt_context.py      # 四层提示词组装引擎
│   │   └── long_memory/knowledge/     # RAG 长期记忆系统
│   │       ├── rag.py                 # RAG 系统总入口（单例）
│   │       ├── rag_retriever.py       # 检索器注册与懒加载
│   │       ├── rag_cache.py           # Redis 缓存层
│   │       ├── rag_formatter.py       # 检索结果格式化
│   │       ├── hybrid_retriever.py    # 混合检索引擎（关键词 + 语义 + 重排序）
│   │       ├── query_rewriter.py      # 医学查询改写器
│   │       ├── embedding_FAISS.py     # BCE 嵌入 + FAISS 向量库
│   │       ├── medical_knowledge.py   # 医学知识库 + 化验异常判断
│   │       ├── reference_ranges.py    # 40+ 种检验指标参考范围
│   │       ├── chunk_strategies.py    # 文档分块策略
│   │       ├── document_loaders.py    # 多格式文档加载器
│   │       ├── text_cleaner.py        # 文本清洗
│   │       ├── main_agent_docs/       # 医学知识源文档
│   │       └── vector_db/main/        # 预构建 FAISS 索引
│   ├── models/                        # 本地模型权重（需自行下载）
│   │   ├── Qwen2.5-7B-Instruct/
│   │   ├── Qwen2.5-3B-Instruct/
│   │   └── bce-embedding-base_v1/
│   └── .env                           # Python 服务配置
├── frontend-vue/                      # Vue 3 前端
│   └── src/
│       ├── components/                # ChatWindow / ChatMessage
│       ├── views/                     # Login
│       ├── stores/                    # Pinia 状态管理
│       └── services/                  # API 请求封装
├── ai-services-python/ocr_service/    # OCR 检验单识别服务
├── test/                              # 测试脚本
│   ├── 终端多轮对话测试.py             # 交互式多轮对话测试
│   ├── create_modle_test.py           # 模型加载 + Agent 创建单元测试
│   ├── 验证RAG.py                     # RAG 接入有效性验证
│   └── 验证检索引擎优化.py             # 混合检索引擎效果验证
├── 大创文档.md                         # 技术架构设计文档
└── README.md                          # 本文件
```

## 快速开始

### 环境要求

- NVIDIA 显卡（≥6GB 显存，推荐 8GB+）或 CPU（推理较慢）
- CUDA 12.4+、Python 3.11、Conda
- Node.js 18+（仅前端）

### 1. 创建环境并安装依赖

```powershell
# 创建 Conda 环境
conda create -n medagent python=3.11 -y
conda activate medagent

# 安装 PyTorch（CUDA 12.4）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 安装核心依赖
pip install transformers accelerate bitsandbytes sentencepiece
pip install fastapi uvicorn pydantic pydantic-settings python-dotenv
pip install sentence-transformers faiss-cpu
pip install redis httpx requests tenacity tiktoken aiofiles

# RAG 检索层依赖（LangChain 封装，待去框架化）
pip install langchain-community langchain-core langchain-text-splitters
```

### 2. 下载模型权重

从 HuggingFace 或 ModelScope 下载以下模型到 `python_service/models/`：

```powershell
# Qwen2.5-7B-Instruct（主模型，~14GB）
# 推荐使用 ModelScope（国内更快）：
python -c "from modelscope import snapshot_download; snapshot_download('qwen/Qwen2.5-7B-Instruct', cache_dir='python_service/models/Qwen2.5-7B-Instruct')"

# bce-embedding-base_v1（嵌入模型，~1GB）
python -c "from huggingface_hub import snapshot_download; snapshot_download('maidalun1020/bce-embedding-base_v1', local_dir='python_service/models/bce-embedding-base_v1')"
```

### 3. 配置环境变量

编辑 `python_service/.env`：

```env
RAG_USE_LOCAL_EMBEDDING=true
LLM_MODEL_PATH=./models/Qwen2.5-7B-Instruct     # 主模型路径
RAG_LOCAL_EMBEDDING_PATH=./models/bce-embedding-base_v1  # 嵌入模型路径
VECTOR_DB_PATH=./harness/long_memory/knowledge/vector_db  # FAISS 索引路径
```

### 4. 运行测试

```powershell
conda activate medagent
cd Medical-agent

# 交互式多轮对话测试
python -u test/终端多轮对话测试.py

# 模型加载单元测试
python -u test/create_modle_test.py

# RAG 有效性验证
python -u test/验证RAG.py

# 检索引擎优化验证
python -u test/验证检索引擎优化.py
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

### Agent 对话流程

```
用户输入 → LabAgent.chat()
    ├─ state.add_message(HumanMessage)
    ├─ _do_rag(query)          ← 混合检索（关键词 + 语义 + 重排序）
    ├─ assemble_final_prompt()  ← 四层组装 + RAG 上下文注入
    ├─ chat_model.invoke()      ← 4-bit 量化推理
    └─ state.add_message(AssistantMessage)
```

---

## 代码修改记录

以下记录了从项目初始状态到当前版本的所有代码变更，按分支 `tbz_1` 提交。

### 1. 环境搭建与模型配置

| 文件 | 修改内容 |
|------|---------|
| `python_service/.env` | 模型路径从 7B 更新；新增 `VECTOR_DB_PATH` 配置项；支持 3B/7B 切换 |
| `python_service/core/config.py` | 修复 `VECTOR_DB_PATH` 的相对路径解析（基于 `BASE_DIR` 而非 CWD）|

**原因**：原配置路径使用 CWD 解析，跨目录运行时找不到模型。改为基于 `python_service/` 目录的绝对路径解析。

### 2. 模型推理层修复

| 文件 | 修改内容 |
|------|---------|
| `python_service/harness/llm_adapter/chat_model.py` | 增强 `ROLE_MARKER_PATTERN` 正则，新增 `#` / `回答完毕` / `停止` 前缀匹配；新增 `STOP_PATTERN` 正则（`#停止#` / `回答完毕` / `#结束#`）；`_truncate_at_role_marker()` 增加停止标记检查 |

**原因**：7B 模型推理时产生幻觉续写，生成 `#停止#Human:` 等伪对话标记。原正则仅匹配 `^`、`\n`、`。！？` 作为前缀，无法覆盖 `#停止#Human:` 变体。修复后所有变体均能被截断，防止污染 AgentState。

### 3. Agent 状态增强

| 文件 | 修改内容 |
|------|---------|
| `python_service/harness/state/agent_state.py` | 新增 `rag_context: str = ""` 字段；`save_snapshot()` 和 `rollback()` 增加 `rag_context` 的持久化和恢复 |

**原因**：为 RAG 接入做准备——每轮对话的 RAG 检索结果需要暂存在状态中供提示词组装使用。

### 4. RAG 接入主对话流程

| 文件 | 修改内容 |
|------|---------|
| `python_service/harness/llm_adapter/create_agent.py` | 新增 `_ensure_rag()` 延迟加载函数（含路径注入和异常降级）；新增 `_do_rag()` 方法，在每轮 `chat()` 和 `chat_stream()` 中自动调用 RAG 检索；`chat()` 和 `chat_stream()` 流程增加 RAG 步骤 |

**原因**：RAG 模块代码完整但从未接入主对话流程——嵌入模型、FAISS 索引、检索器都已就绪，但 `LabAgent.chat()` 没有调用。接入后每轮对话自动检索医学知识库并注入 prompt。

### 5. 提示词 RAG 注入

| 文件 | 修改内容 |
|------|---------|
| `python_service/harness/prompt/prompt_context.py` | `assemble_final_prompt()` 增加 RAG 层：当 `state.rag_context` 非空时，在 Layer 2（任务指令）和 Layer 3（历史对话）之间插入 `【参考医学知识库】` 提示块 |

**原因**：RAG 检索到的医学知识需要注入 prompt 才能被模型使用。插入位置在任务指令之后、历史对话之前，确保模型优先参考知识库内容回答。

### 6. RAG 路径修复

| 文件 | 修改内容 |
|------|---------|
| `python_service/harness/long_memory/knowledge/embedding_FAISS.py` | `resolve_embedding_model_source()` 增加相对路径解析：基于 `__file__` 推导 `python_service/` 目录，将 `./models/` 等相对路径转为绝对路径 |

**原因**：嵌入模型路径依赖 CWD，在项目根目录运行时找不到模型。修复后与 LLM 路径解析逻辑一致。

### 7. 检索引擎优化（阶段二）

#### 7.1 查询改写器（新增）

**文件**：`python_service/harness/long_memory/knowledge/query_rewriter.py`

- 60+ 医学指标缩写 → 中文全称映射（如 `Cr` → `血肌酐 肾功能`）
- 30 组口语表述 → 医学术语扩展（如 `偏高` → `升高 高于正常 参考范围 异常原因`）
- 指标提取函数：英文缩写匹配（CJK 字符兼容边界）+ 中文指标名匹配

#### 7.2 混合检索引擎（新增）

**文件**：`python_service/harness/long_memory/knowledge/hybrid_retriever.py`

- **关键词匹配层**：从 `reference_ranges.py`（40+ 指标）精确匹配参考范围，三层策略（代码 → 中文名 → 系统关键词），最多返回 5 篇
- **语义检索层**：复用原有 FAISS 检索器
- **重排序**：按关键词命中率加权（指标缩写权重 ×2）
- **截断**：文档超过 600 字符时在句号/换行处截断
- **去重**：按内容指纹（前 100 字符）去重

#### 7.3 RAG 系统集成

**文件**：`python_service/harness/long_memory/knowledge/rag.py`

- `RAGSystem` 增加 `hybrid_retriever` 和 `_get_faiss_retriever()` 
- `retrieve()` 方法改为混合检索路线（查询改写 → reference_ranges 匹配 → FAISS 语义 → 重排序截断），纯语义检索作为回退

### 8. 测试脚本

| 文件 | 修改/新增 | 说明 |
|------|-----------|------|
| `test/终端多轮对话测试.py` | 重写 docstring | 移除含 Unicode 转义冲突的旧示例输出；更新 Conda 环境名 |
| `test/create_modle_test.py` | 修复 | 模型路径从 `models/` 修正为 `python_service/models/`；`agent.history` 改为 `agent.state.messages` |
| `test/验证RAG.py` | **新增** | RAG 接入验证：直接检索 → Agent 对话 → state.rag_context 检查 → 回复内容分析 |
| `test/验证检索引擎优化.py` | **新增** | 检索引擎优化验证：查询改写 → 精确匹配 → 混合检索对比 → Agent 端到端 |

### 9. 文档

| 文件 | 修改内容 |
|------|---------|
| `大创文档.md` | 补充"记忆管理"章节（~400 行）：三层记忆架构、瞬时/短期/长期记忆实现细节、RAG 系统完整文档（嵌入模型、向量数据库、检索流程、缓存层、知识库、数据流） |
| `README.md` | **新增** 项目说明文档（本文件） |

### 10. 依赖安装

在 `medagent` Conda 环境中新增安装：

```
langchain-community  langchain-core  langchain-text-splitters
redis  modelscope
```

---

## 当前开发进度

| 模块 | 状态 |
|------|------|
| 模型加载层（llm_core） | ✅ 完成 |
| 推理适配器（llm_adapter） | ✅ 完成 |
| Agent 状态管理（state） | ✅ 完成 |
| 四层提示词（prompt） | ✅ 完成 |
| RAG 集成（接入主流程） | ✅ 完成 |
| 检索引擎优化（查询改写 + 混合检索 + 重排序） | ✅ 完成 |
| AgentLoop 调度循环 | 🔲 待开发 |
| 工具系统 | 🔲 待开发 |
| RAG 去 LangChain 化 | 🔲 待开发 |
| 前端联调 | 🔲 待开发 |

## 分支说明

| 分支 | 说明 |
|------|------|
| `zly_3` | 原始分支，项目初始状态 |
| `tbz_1` | 当前分支，包含上述所有代码修改 |
