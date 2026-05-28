# 技术文档 1：模型加载与 Agent 创建

## 1. 文档概述

本文档详细说明 MedLabAgent 系统中 LLM 模型的加载机制和 Agent 的创建流程，涵盖从模型权重加载到 Agent 实例化的完整链路。

---

## 2. 相关目录与文件

```
python_service/
├── core/
│   └── config.py                    # 全局配置（Pydantic BaseSettings）
├── harness/
│   ├── __init__.py                  # 对外导出 ModelLoader, ChatModel, AgentState
│   ├── llm_core/
│   │   ├── __init__.py
│   │   └── model_loader.py          # 模型加载器（单例 + 懒加载 + 量化回退）
│   ├── llm_adapter/
│   │   ├── __init__.py
│   │   ├── chat_model.py            # 推理适配器（invoke/stream，零框架依赖）
│   │   └── create_agent.py          # Agent 工厂（LabAgent 创建 + 工具注册）
│   ├── state/
│   │   └── agent_state.py           # Agent 状态与消息类型
│   └── prompt/
│       └── prompt_context.py        # 四层提示词组装
└── models/
    ├── Qwen2.5-7B-Instruct/         # 主模型权重
    └── bce-embedding-base_v1/        # 嵌入模型权重
```

---

## 3. 全局配置（config.py）

使用 Pydantic `BaseSettings` 统一管理，从 `python_service/.env` 加载环境变量。

### 3.1 LLM 相关配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LLM_MODEL_PATH` | `<project>/models/Qwen2.5-7B-Instruct` | 模型权重本地路径 |
| `LLM_USE_4BIT` | `True` | 是否启用 4-bit 量化 |
| `LLM_4BIT_QUANT_TYPE` | `"nf4"` | 量化类型（QLoRA 推荐） |
| `LLM_4BIT_USE_DOUBLE_QUANT` | `True` | 是否启用双重量化（进一步节省显存） |
| `USE_MOCK_LLM` | `False` | 是否使用 Mock LLM（测试用） |
| `TEMPERATURE` | `0.7` | 生成温度 |
| `MAX_TOKENS` | `2000` | 单次生成最大 token 数 |

### 3.2 RAG 相关配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `VECTOR_DB_TYPE` | `"faiss"` | 向量数据库类型 |
| `VECTOR_DB_PATH` | `<python_service>/knowledge/vector_db` | 向量库路径 |
| `RAG_TOP_K` | `3` | 检索返回文档数 |
| `RAG_LOCAL_EMBEDDING_PATH` | `<project>/models/bce-embedding-base_v1` | 本地嵌入模型路径 |
| `RAG_EMBEDDING_DEVICE` | `"cpu"` | 嵌入模型运行设备 |
| `RAG_CACHE_TTL_SECONDS` | `86400` | RAG 缓存过期时间（24h） |

---

## 4. 模型加载器（ModelLoader）

**文件**：`python_service/harness/llm_core/model_loader.py`

### 4.1 设计模式

采用 **单例模式 + 双重检查锁（DCL） + 懒加载**：

- **单例**：全局唯一实例，通过 `ModelLoader.init(config)` 初始化，后续 `ModelLoader()` 返回同一实例
- **DCL**：`threading.Lock` 保证线程安全，避免并发场景下重复加载
- **懒加载**：模型不在构造时加载，而是在首次访问 `model` 或 `tokenizer` 属性时触发

### 4.2 ModelConfig 数据类

```python
@dataclass
class ModelConfig:
    model_path: str              # 本地模型目录路径
    use_4bit: bool = True        # 启用 4-bit 量化
    quant_type: str = "nf4"      # 量化类型
    use_double_quant: bool = True # 双重量化
    temperature: float = 0.7     # 生成温度
    max_new_tokens: int = 2000   # 最大生成 token 数
```

### 4.3 加载流程

```
ModelLoader.init(config)
    │
    ├─ 重置 _instance = None
    └─ 创建新实例 → ModelLoader(config)
                        │
                        └─ 首次访问 .model / .tokenizer
                            │
                            └─ load()
                                │
                                ├─ 1. 快速检查（无锁）：已加载则直接返回
                                │
                                ├─ 2. 加锁 + 二次检查：防止并发重复加载
                                │
                                ├─ 3. 解析量化配置 _resolve_quantization_config()
                                │       ├─ use_4bit=False → None（不量化）
                                │       ├─ CUDA 不可用 → 警告 + None
                                │       ├─ bitsandbytes 未安装 → 警告 + None
                                │       └─ 正常 → BitsAndBytesConfig(
                                │               load_in_4bit=True,
                                │               bnb_4bit_quant_type="nf4",
                                │               bnb_4bit_use_double_quant=True,
                                │               bnb_4bit_compute_dtype=torch.float16
                                │           )
                                │
                                ├─ 4. 加载分词器
                                │       AutoTokenizer.from_pretrained(
                                │           path, trust_remote_code=True,
                                │           local_files_only=True
                                │       )
                                │
                                ├─ 5. 构建模型参数
                                │       ├─ 有量化: quantization_config + device_map={"": 0}
                                │       └─ 无量化: torch_dtype=float16(GPU)/float32(CPU)
                                │               + device_map="auto"/None
                                │
                                ├─ 6. 加载模型
                                │       AutoModelForCausalLM.from_pretrained(path, **kwargs)
                                │
                                ├─ 7. CPU 回退（无量化且无 GPU 时）
                                │       model.to("cpu")
                                │
                                ├─ 8. 切换推理模式
                                │       model.eval()
                                │
                                └─ 9. 写入类变量 _tokenizer / _model
```

### 4.4 量化回退链

```
4-bit 量化 (bitsandbytes NF4)
    │
    ├─ CUDA 可用 + bitsandbytes 已安装 → 正常 4-bit 量化
    │
    ├─ CUDA 不可用 → 回退到 fp32 CPU 推理
    │
    └─ bitsandbytes 未安装 → 回退到 fp16（GPU）或 fp32（CPU）
```

---

## 5. 推理适配器（ChatModel）

**文件**：`python_service/harness/llm_adapter/chat_model.py`

### 5.1 设计原则

**零框架依赖**：仅依赖 `torch` 和 `transformers`，不依赖 LangChain/LangGraph。接收组装好的 prompt 字符串，执行推理，返回文本。

### 5.2 核心能力

| 方法 | 说明 |
|------|------|
| `invoke(prompt)` | 同步推理，返回完整文本 |
| `stream(prompt)` | 流式推理，逐 token 返回 `Chunk` 对象 |

### 5.3 invoke 同步流程

```
invoke(prompt)
    │
    ├─ 1. _build_inputs(prompt)
    │       tokenize → tensor → 移至 CUDA:0（如可用）
    │
    ├─ 2. model.generate() （torch.inference_mode 下）
    │       参数: max_new_tokens, do_sample, temperature, pad_token_id, eos_token_id
    │
    ├─ 3. 切片输出：去掉 prompt 部分，仅保留生成的 token
    │
    ├─ 4. 解码 → strip → 修复乱码 → 截断角色标记
    │
    └─ 5. 返回干净文本
```

### 5.4 stream 流式流程

```
stream(prompt)
    │
    ├─ 1. _build_inputs(prompt)
    │
    ├─ 2. 创建 TextIteratorStreamer（skip_prompt=True, skip_special_tokens=True）
    │
    ├─ 3. 在守护线程中启动 model.generate(streamer=streamer)
    │
    ├─ 4. 主线程迭代 streamer tokens:
    │       ├─ 修复乱码
    │       ├─ 检测角色标记 → 如发现则截断并返回
    │       └─ 尾部 32 字符缓冲区处理边界 token
    │
    └─ 5. yield 剩余文本
```

采用 **生产者-消费者模式**：模型在后台线程生成，主线程逐块 yield。

### 5.5 文本净化工具

| 函数 | 作用 |
|------|------|
| `_count_cjk(text)` | 统计中文字符数 |
| `_looks_like_mojibake(text)` | 检测编码乱码（"Ã", "Â" 等异常字节 + 中文字符 < 3） |
| `_repair_mojibake(text)` | 尝试通过 latin1/cp1252 → utf-8 重新编码修复 |
| `_truncate_at_role_marker(text)` | 正则匹配 `Human:/User:/Assistant:/System:` 并截断，防止幻觉溢出 |

---

## 6. Agent 工厂（create_agent.py）

**文件**：`python_service/harness/llm_adapter/create_agent.py`

### 6.1 数据结构

```python
@dataclass
class Tool:
    name: str                        # 工具名称
    description: str                 # 工具描述
    func: Callable[[str], str]       # 工具执行函数
```

### 6.2 LabAgent 类

构造参数：`ChatModel`、`AgentState`、可选 `Tool` 列表。

| 方法 | 说明 |
|------|------|
| `chat(user_input)` | 同步对话 |
| `chat_stream(user_input)` | 流式对话 |
| `call_tool(tool_name, args)` | 调用指定工具 |
| `register_tool(tool)` | 注册新工具 |
| `reset()` | 重置状态（保留 SystemMessage） |

### 6.3 chat 同步对话流程

```
chat(user_input)
    │
    ├─ 1. state.add_message(HumanMessage(user_input))
    │
    ├─ 2. assemble_final_prompt(state)  ← 四层提示词组装
    │
    ├─ 3. chat_model.invoke(prompt)     ← 模型推理
    │
    ├─ 4. state.add_message(AssistantMessage(reply))
    │
    └─ 5. return reply
```

### 6.4 chat_stream 流式对话流程

```
chat_stream(user_input)
    │
    ├─ 1. state.add_message(HumanMessage(user_input))
    │
    ├─ 2. assemble_final_prompt(state)
    │
    ├─ 3. for chunk in chat_model.stream(prompt):
    │       累积完整回复
    │       yield chunk
    │
    ├─ 4. state.add_message(AssistantMessage(full_reply))
    │
    └─ 5. return
```

### 6.5 create_agent() 工厂函数

```python
create_agent(
    user_id, model_path, system_prompt,
    use_4bit, temperature, max_new_tokens,
    tools, user_name, user_age, user_gender
) → LabAgent
```

**执行流程**：

```
create_agent()
    │
    ├─ 1. 解析模型路径
    │       ├─ 未指定 → 读取 LLM_MODEL_PATH 环境变量
    │       ├─ 相对路径 → 相对于 python_service/ 目录解析
    │       └─ 默认回退 → <project>/models/Qwen2.5-7B-Instruct
    │
    ├─ 2. 创建 UserProfile
    │       UserProfile(user_id, name, age, gender)
    │
    ├─ 3. 构建系统提示词
    │       build_system_prompt(user, system_prompt)
    │
    ├─ 4. 初始化模型
    │       ModelConfig(model_path, use_4bit, temperature, max_new_tokens)
    │       ModelLoader.init(config)    ← 单例初始化
    │       ChatModel(loader)           ← 包装为推理适配器
    │
    ├─ 5. 创建状态
    │       AgentState(user=user)
    │       state.add_message(SystemMessage(system_prompt))
    │
    └─ 6. 组装 Agent
            LabAgent(chat_model, state, tools)
```

---

## 7. 完整调用链路图

```
用户请求
    │
    ▼
create_agent() ─── 工厂函数
    │
    ├─ ModelConfig ─── 配置数据类
    │
    ├─ ModelLoader.init(config) ─── 单例初始化
    │       │
    │       └─ .model / .tokenizer ─── 懒加载触发
    │               │
    │               └─ load()
    │                       ├─ _resolve_quantization_config() ─── 量化回退链
    │                       ├─ AutoTokenizer.from_pretrained()
    │                       ├─ AutoModelForCausalLM.from_pretrained()
    │                       └─ model.eval()
    │
    ├─ ChatModel(loader) ─── 推理适配器
    │       ├─ invoke(prompt) ─── 同步推理
    │       └─ stream(prompt) ─── 流式推理
    │
    ├─ AgentState(user) ─── 状态容器
    │       └─ SystemMessage ─── 系统提示词
    │
    └─ LabAgent(chat_model, state) ─── Agent 实例
            ├─ chat(input) ─── 同步对话
            └─ chat_stream(input) ─── 流式对话
```

---

## 8. 关键设计决策

| 决策 | 原因 |
|------|------|
| 单例模式 | 全局只需一个模型实例，避免重复加载 7B 模型的显存开销 |
| 懒加载 | 启动时不加载模型，首次请求时才加载，加快服务启动 |
| 双重检查锁 | 保证多线程安全，避免并发请求时重复初始化 |
| 零框架依赖 | 核心推理层不依赖 LangChain，降低耦合，便于独立测试和替换 |
| 量化回退链 | 兼容不同硬件环境（有/无 GPU、有/无 bitsandbytes） |
| 本地文件加载 | `local_files_only=True`，避免运行时网络请求 |
