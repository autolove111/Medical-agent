# Loop 与路由回调机制

## 1. 整体架构

```
用户消息
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI 路由层  api/routes/chat.py                          │
│                                                              │
│  GET /api/chat/react-stream                                  │
│    │                                                         │
│    ├─ 1. _get_or_create_loop(user_id, session_id)            │
│    │     → 缓存 analyze_ReActLoop 实例                       │
│    │                                                         │
│    ├─ 2. 创建 asyncio.Queue                                  │
│    │                                                         │
│    ├─ 3. 在线程池中启动 loop.run(query, emit=queue.put)      │
│    │                                                         │
│    └─ 4. event_generator() 异步从 queue 读取 → yield SSE     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
  │ SSE: data: {"type":"thought","content":"..."}\n\n
  ▼
前端 fetch ReadableStream → 渲染
```

---

## 2. 路由层详解

### 2.1 实例缓存

**文件**：[chat.py:51-62](python_service/api/routes/chat.py#L51-L62)

```python
_loops: dict[tuple, analyze_ReActLoop] = {}

def _get_or_create_loop(user_id: str, session_id: str, max_steps: int = 5):
    key = (user_id, session_id)
    if key not in _loops:
        _loops[key] = analyze_ReActLoop(user_id=user_id, session_id=session_id, max_steps=max_steps)
    return _loops[key]
```

**设计意图**：同一个 `(user_id, session_id)` 对应一个 `analyze_ReActLoop` 实例，实例内部持有 `LabAgent` → `MemorySystem` → `ShortMemoryStore`，短期记忆在同一个会话内持续累积。

### 2.2 SSE 流式端点

**文件**：[chat.py:92-124](python_service/api/routes/chat.py#L92-L124)

```python
@router.get("/chat/react-stream")
async def chat_react_stream(user_id, session_id, message, report_id, max_steps):
    loop = _get_or_create_loop(user_id, session_id, max_steps)

    query = []
    if report_id:
        query.append(_build_report_context(report_id))  # 化验报告上下文
    query.append(message)                                 # 用户消息

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        def emit(event: dict):
            queue.put_nowait(event)          # ← 回调：ReAct 循环往队列丢事件

        def blocking_run():
            try:
                loop.run(query, emit=emit)   # ← 在线程池中执行
            except Exception as e:
                queue.put_nowait({"type": "error", "message": str(e)})
            finally:
                queue.put_nowait(None)       # ← 哨兵值，表示结束

        executor = ThreadPoolExecutor(max_workers=1)
        asyncio.get_event_loop().run_in_executor(executor, blocking_run)

        while True:
            event = await asyncio.wait_for(queue.get(), timeout=180.0)
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**关键机制**：

| 组件 | 作用 |
|------|------|
| `emit` 回调 | ReAct 循环通过它推送事件，与 SSE 解耦 |
| `asyncio.Queue` | 线程安全的桥梁，连接同步的 ReAct 循环和异步的 SSE 生成器 |
| `ThreadPoolExecutor` | ReAct 循环是同步阻塞的，必须放线程池才不会阻塞事件循环 |
| `None` 哨兵 | 标记流结束，`event_generator` 据此 break |
| `wait_for(timeout=180)` | 防止推理卡死，超时返回错误 |

### 2.3 历史加载端点

**文件**：[chat.py:75-90](python_service/api/routes/chat.py#L75-L90)

```python
@router.get("/chat/history")
async def get_chat_history(user_id, session_id):
    snapshot = MemorySnapshotMemory(MemorySnapshotRepo())
    data = snapshot.load(user_id, session_id)   # 取最新快照
    if not data:
        return {"code": 200, "data": {"messages": []}}

    messages = [
        m for m in data["messages"]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return {"code": 200, "data": {"messages": messages}}
```

**过滤逻辑**：快照中的 messages 包含 `tool_calls` 和 `tool` 消息（FC 格式），前端只需要 `user` + `assistant` 文本消息。

---

## 3. ReAct 循环详解

### 3.1 analyze_ReActLoop

**文件**：[analyze_ReAct_loop.py](python_service/harness/agentic_loop/analyze_ReAct_loop.py)

#### 初始化

```python
class analyze_ReActLoop:
    def __init__(self, user_id, session_id, max_steps=5):
        self.agent = LabAgent(
            user_id=user_id,
            session_id=session_id,
            def_prompt="你是一个医疗助手，分析患者的检验结果并提供建议。",
            format_prompt="请严格按照以下 ReAct 框架工作：..."
        )
        self.max_steps = max_steps
```

#### run() 方法流程

```python
def run(self, user_query: list[str], emit=None) -> str:
    self.step_count = 0
    emit({"type": "react_start", "query": str(user_query)})

    # ① 先从快照恢复历史（修复：必须在写入新消息之前）
    self.agent.get_short_memory_text()

    # ② 写入新消息到短期记忆
    for query in user_query:
        self.agent.write_user_message_to_memory(query)

    try:
        while self.step_count < self.max_steps:
            self.step_count += 1
            emit({"type": "step_start", "step": self.step_count})

            # ③ 组装 prompt（system + summary + history + new message）
            message_prompt = self.agent.get_message_prompt()

            # ④ 调用 LLM
            response = self.agent.chat(message_prompt=message_prompt)
            assistant_message = response.choices[0].message

            # ⑤ 分支处理
            if assistant_message.tool_calls:
                # 工具调用 → 执行 → 写入记忆 → 继续循环
                self.agent.write_tool_calls_to_memory(...)
                for tool_call in assistant_message.tool_calls:
                    observation = self.agent.execute_tool(...)
                    self.agent.write_tool_result_to_memory(...)
                    emit({"type": "observation", ...})
                continue

            if finish_reason == "stop":
                # 纯文本回复 → 写入记忆 → 结束
                self.agent.write_assistant_message_to_memory(...)
                emit({"type": "final_answer", "content": ...})
                emit({"type": "react_end"})
                return assistant_message.content

    finally:
        # ⑥ 保存快照到 PostgreSQL
        self.agent.memory.save_snapshot()
```

### 3.2 事件类型

| type | 何时触发 | 携带字段 | 前端处理 |
|------|----------|----------|----------|
| `react_start` | 循环开始 | `query` | 可选：显示加载 |
| `step_start` | 每步开始 | `step` | 可选：显示步骤号 |
| `thought` | LLM 返回 content（有 tool_calls 时） | `step`, `content` | 推理步骤面板 |
| `tool_call` | LLM 返回 tool_calls | `step`, `name`, `args` | 推理步骤面板 |
| `observation` | 工具执行完成 | `step`, `name`, `result` | 推理步骤面板 |
| `final_answer` | LLM 返回纯文本（finish_reason=stop） | `content` | 消息正文 |
| `react_end` | 循环结束 | 无 | 清理状态 |
| `error` | 异常 | `message` | 错误提示 |

---

## 4. Agent 层

### 4.1 LabAgent

**文件**：[create_agent.py](python_service/harness/llm_adapter/create_agent.py)

```python
class LabAgent:
    def __init__(self, user_id, session_id, def_prompt, format_prompt):
        self.memory = MemorySystem(user_id, session_id)  # 记忆系统
        self.chat_model = ChatModel()                      # LLM 调用
        self.system_prompt = SystemPromptBuilder()          # prompt 构建
        self.tool_registry = get_registry()                 # 工具注册表
```

#### 记忆读写方法

| 方法 | 作用 | 写入目标 |
|------|------|----------|
| `write_user_message_to_memory(text)` | 用户消息 | events（PG） + 短期记忆 |
| `write_assistant_message_to_memory(text)` | 助手回复 | events（PG） + 短期记忆 |
| `write_tool_calls_to_memory(content, tool_calls)` | 工具调用请求 | 短期记忆 |
| `write_tool_result_to_memory(id, result)` | 工具执行结果 | 短期记忆 |
| `get_short_memory_text()` | 读取短期记忆 | 快照 → 短期记忆 |
| `get_message_prompt()` | 组装完整 prompt | system + summary + history |

#### get_message_prompt() 组装逻辑

```python
def get_message_prompt(self) -> list[dict]:
    messages = []
    messages.extend(self.get_system_prompt())      # system 定义 + ReAct 指令 + summary
    messages.extend(self.get_short_memory_text())  # user/assistant/tool 历史消息
    return messages
```

最终传给 LLM 的 messages 结构：

```json
[
  {"role": "system", "content": "你是一个医疗助手..."},
  {"role": "system", "content": "请严格按照以下 ReAct 框架工作..."},
  {"role": "system", "content": "会话摘要：..."},
  {"role": "user", "content": "头疼"},
  {"role": "assistant", "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "call_xxx", "content": "..."},
  {"role": "assistant", "content": "您好！您提到头疼..."}
]
```

---

## 5. MemorySystem

**文件**：[memory/__init__.py](python_service/harness/memory/__init__.py)

```python
class MemorySystem:
    def __init__(self, userid, session_id, db_session=None):
        self._stm = ShortMemoryStore()                        # 短期记忆（内存）
        self.events = EventsRecordMemory(userid, repo)         # 对话记录（PG）
        self.snapshot = MemorySnapshotMemory(repo)             # 快照（PG）
        self.profile = ProfileMemory(repo, userid)             # 患者画像（PG）
```

### 写入流程

```
用户消息 → on_user_message(text)
             ├── events.append("user", text)      → PG session_data 表
             └── _stm.add_user_message(text)       → 内存 messages[]

助手回复 → on_assistant_message(text)
             ├── events.append("assistant", text)  → PG session_data 表
             └── _stm.add_assistant_message(text)  → 内存 messages[]

工具调用 → on_assistant_tool_calls(content, tool_calls)
             └── _stm.add_assistant_tool_calls()   → 内存 messages[]

工具结果 → on_tool_result(tool_call_id, content)
             └── _stm.add_tool_result()            → 内存 messages[]
```

### 快照流程

```
save_snapshot()
  └── snapshot.save(patient_id, session_id, messages, summary, message_len)
        └── INSERT INTO short_memory_snapshot ...

load_snapshot()
  └── snapshot.load(patient_id, session_id)
        └── SELECT ... ORDER BY id DESC LIMIT 1
        └── 覆盖 _stm.messages, _stm.summary, _stm.message_len
```

---

## 6. 快照加载时序（已修复）

### 问题

```python
# 修复前
for query in user_query:
    self.agent.write_user_message_to_memory(query)  # 先写 → _stm.messages 非空
message_prompt = self.agent.get_message_prompt()     # get_short_memory_text() 不为空
                                                  # → 跳过 load_snapshot() → 历史丢失
```

### 修复后

```python
# 修复后
self.agent.get_short_memory_text()                   # 先读 → _stm 为空 → 加载快照
for query in user_query:
    self.agent.write_user_message_to_memory(query)   # 再写 → 新消息追加到历史之后
message_prompt = self.agent.get_message_prompt()     # 包含历史 + 新消息
```

---

## 7. 短期记忆压缩

**文件**：[store.py](python_service/harness/memory/short_memory/store.py)

当 `message_len` 超过 `ContextWindowControl` 的 history 限制时，触发压缩：

```python
def compress_messages(self, summary_len):
    # 1. 取最早的一半消息
    mid = len(self.messages) // 2
    old_messages = self.messages[:mid]

    # 2. 拼接已有摘要 + 待压缩对话
    # 3. 调用 LLM 生成压缩摘要
    # 4. 更新 summary，删除已压缩的 messages
    # 5. 重新计算 message_len
```

压缩后：
- `summary` 包含压缩后的要点（FC 格式）
- `messages` 只保留后半部分
- `message_len` 重新计算
