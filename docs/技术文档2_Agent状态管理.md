# 技术文档 2：Agent 状态管理

## 1. 文档概述

本文档详细说明 MedLabAgent 系统中 Agent 状态的管理机制，包括消息类型体系、用户画像、状态容器、快照与回滚等功能。

---

## 2. 相关目录与文件

```
python_service/
└── harness/
    ├── state/
    │   ├── __init__.py
    │   └── agent_state.py      # 消息类型 + UserProfile + AgentState
    └── llm_adapter/
        └── create_agent.py      # Agent 创建时的状态初始化
```

---

## 3. 消息类型体系

**文件**：`python_service/harness/state/agent_state.py`

### 3.1 类型继承关系

```
BaseMessage（抽象基类）
    │   content: str
    │   role: str（由子类指定）
    │
    ├─ SystemMessage      role = "system"
    ├─ HumanMessage       role = "user"
    ├─ AssistantMessage    role = "assistant"
    └─ ToolMessage        role = "tool"
                            ├─ tool_name: str
                            └─ tool_args: str
```

### 3.2 各消息类型说明

| 类型 | role 值 | 用途 | 额外字段 |
|------|---------|------|----------|
| `BaseMessage` | (抽象) | 所有消息的基类，定义 `content` 和 `role` | — |
| `SystemMessage` | `"system"` | 系统提示词，定义 Agent 身份和行为规则 | — |
| `HumanMessage` | `"user"` | 用户输入的消息 | — |
| `AssistantMessage` | `"assistant"` | Agent 生成的回复 | — |
| `ToolMessage` | `"tool"` | 工具调用的结果 | `tool_name`, `tool_args` |

### 3.3 设计特点

- 所有消息均为 `@dataclass`，不可变语义
- `role` 和 `content` 属性直接兼容 `ChatModel` 的 prompt 组装
- `ToolMessage` 扩展了工具调用的元信息，支持未来的工具链路追踪

---

## 4. 用户画像（UserProfile）

### 4.1 数据结构

```python
@dataclass
class UserProfile:
    user_id: str                           # 用户唯一标识
    name: str = ""                         # 姓名
    age: int = 0                           # 年龄
    gender: str = ""                       # 性别："男" / "女"
    medical_history: List[str] = []        # 既往病史
    allergies: List[str] = []              # 过敏史
    current_medications: List[str] = []    # 当前用药
```

### 4.2 设计意图

专为医疗场景设计。年龄、性别直接影响参考范围的判断，既往病史和用药情况影响诊断建议：

- **年龄**：不同年龄段的检验参考值不同（如新生儿 vs 成人 vs 老年人）
- **性别**：部分指标存在性别差异（如肌酐、血红蛋白）
- **既往病史**：影响异常指标的可能原因分析
- **当前用药**：某些药物会导致特定指标异常

### 4.3 在提示词中的呈现

通过 `user_to_prompt_text(user)` 转换为文本格式：

```
用户ID: u001 | 姓名: 张三 | 年龄: 45岁 | 性别: 男 | 既往病史: 糖尿病, 高血压
```

仅包含非空字段，避免无用信息占用 context 窗口。

---

## 5. Agent 状态容器（AgentState）

### 5.1 数据结构

```python
@dataclass
class AgentState:
    # ── 核心状态 ──
    user: UserProfile                          # 用户画像
    messages: List[BaseMessage] = []           # 对话消息列表

    # ── 推理与规划 ──
    reasoning_process: str = ""                # 当前推理链
    task_queue: List[str] = []                 # 待办任务队列

    # ── 记忆 ──
    memory_ref: Optional[str] = None           # 长期记忆引用

    # ── 执行控制 ──
    is_finished: bool = False                  # 是否结束

    # ── 快照（内部） ──
    _snapshots: List[dict] = []                # 状态快照栈
```

### 5.2 字段分类说明

#### 核心状态

| 字段 | 类型 | 说明 |
|------|------|------|
| `user` | `UserProfile` | 用户画像，包含年龄、性别、病史等医疗信息 |
| `messages` | `List[BaseMessage]` | 完整的对话消息列表，按时间顺序排列 |

#### 推理与规划

| 字段 | 类型 | 说明 |
|------|------|------|
| `reasoning_process` | `str` | 当前推理链文本，记录 Agent 的思考过程 |
| `task_queue` | `List[str]` | 待办任务队列，支持多步骤推理规划 |

#### 记忆

| 字段 | 类型 | 说明 |
|------|------|------|
| `memory_ref` | `Optional[str]` | 长期记忆引用，指向外部存储的知识片段 |

#### 执行控制

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_finished` | `bool` | 标记当前任务是否完成 |

---

## 6. 消息操作 API

### 6.1 基础操作

| 方法 | 说明 |
|------|------|
| `add_message(message)` | 追加消息到 `messages` 列表末尾 |
| `get_messages()` | 返回完整的消息列表（有序） |
| `get_last_assistant_message()` | 反向扫描，返回最近一条 `AssistantMessage` |
| `get_last_human_message()` | 反向扫描，返回最近一条 `HumanMessage` |

### 6.2 消息过滤（属性）

| 属性 | 说明 |
|------|------|
| `human_messages` | 返回所有 `HumanMessage` 实例 |
| `assistant_messages` | 返回所有 `AssistantMessage` 实例 |
| `tool_messages` | 返回所有 `ToolMessage` 实例 |
| `turn_count` | 返回 `HumanMessage` 数量（对话轮次计数器） |

### 6.3 使用示例

```python
state = AgentState(user=UserProfile(user_id="u001"))

# 添加消息
state.add_message(SystemMessage("你是一个医疗助手"))
state.add_message(HumanMessage("我的血糖偏高怎么办？"))
state.add_message(AssistantMessage("血糖偏高可能有以下原因..."))

# 查询
state.turn_count                    # → 1
state.get_last_assistant_message()  # → AssistantMessage("血糖偏高可能...")
state.human_messages                # → [HumanMessage("我的血糖偏高怎么办？")]
```

---

## 7. 快照与回滚机制

### 7.1 设计目的

支持多步推理场景下的状态回退。当 Agent 的推理路径走偏时，可以回滚到之前的状态重新推理。

### 7.2 save_snapshot()

```python
def save_snapshot(self):
    snapshot = {
        "messages": deepcopy(self.messages),
        "reasoning_process": self.reasoning_process,
        "task_queue": self.task_queue[:],
        "memory_ref": self.memory_ref,
        "is_finished": self.is_finished,
    }
    self._snapshots.append(snapshot)
```

将当前状态深拷贝后压入 `_snapshots` 栈。

### 7.3 rollback()

```python
def rollback(self) -> bool:
    if not self._snapshots:
        return False
    snapshot = self._snapshots.pop()
    self.messages = snapshot["messages"]
    self.reasoning_process = snapshot["reasoning_process"]
    self.task_queue = snapshot["task_queue"]
    self.memory_ref = snapshot["memory_ref"]
    self.is_finished = snapshot["is_finished"]
    return True
```

弹出最近的快照并恢复状态。返回 `True` 表示成功，`False` 表示无快照可回滚。

### 7.4 状态转换图

```
正常对话流程:
    [初始状态]
        │
        ├─ add_message(HumanMessage)
        ├─ add_message(AssistantMessage)
        ├─ save_snapshot()  ← 保存检查点
        │
        ▼
    [对话进行中]
        │
        ├─ 推理成功 → 继续对话
        │
        └─ 推理失败 → rollback() → [恢复到检查点] → 重新推理
```

---

## 8. 状态重置

### 8.1 reset()

```python
def reset(self):
    self.messages = [m for m in self.messages if isinstance(m, SystemMessage)]
    self.reasoning_process = ""
    self.task_queue = []
    self.memory_ref = None
    self.is_finished = False
    self._snapshots = []
```

**保留**：所有 `SystemMessage`（系统提示词是持久的）

**清除**：
- 对话消息（Human、Assistant、Tool）
- 推理过程
- 任务队列
- 记忆引用
- 完成标记
- 所有快照

---

## 9. 序列化

### 9.1 to_dict()

```python
def to_dict(self) -> dict:
    return {
        "user": {
            "user_id": self.user.user_id,
            "name": self.user.name,
            "age": self.user.age,
            "gender": self.user.gender,
        },
        "message_count": len(self.messages),
        "turn_count": self.turn_count,
        "reasoning_process": self.reasoning_process,
        "task_queue": self.task_queue,
        "is_finished": self.is_finished,
    }
```

用于日志记录和持久化，不包含完整消息内容（避免序列化过大）。

---

## 10. 状态在对话流程中的流转

```
用户发送消息 "我的肌酐偏高"
    │
    ▼
AgentState 流转:
    │
    ├─ 1. add_message(HumanMessage("我的肌酐偏高"))
    │       messages: [System, Human]
    │
    ├─ 2. assemble_final_prompt(state)  ← 读取 state 构建提示词
    │       读取: messages, user, task_queue
    │
    ├─ 3. chat_model.invoke(prompt)     ← 模型推理
    │
    ├─ 4. add_message(AssistantMessage("肌酐偏高可能..."))
    │       messages: [System, Human, Assistant]
    │
    └─ 5. state 完整保留，等待下一轮对话
            turn_count: 1
            reasoning_process: ""（可选填充）
```

---

## 11. 关键设计决策

| 决策 | 原因 |
|------|------|
| 消息类型分层 | 不同角色的消息有不同的语义和字段需求，分层使类型安全且可扩展 |
| UserProfile 独立 | 用户信息与对话解耦，便于持久化和跨会话复用 |
| 快照栈 | 支持多步推理的回退，无需外部状态机 |
| 保留 SystemMessage | 重置对话时保留系统提示词，保证 Agent 身份一致性 |
| to_dict 不含全文 | 日志序列化时避免过大，完整消息通过消息列表单独管理 |
| dataclass 设计 | 轻量级，无额外依赖，字段默认值清晰 |
