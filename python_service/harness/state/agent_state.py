"""
state.agent_state
~~~~~~~~~~~~~~~~~
自研 Agent 状态管理：定义消息类型、用户画像、Agent 状态。

核心设计：
- 多态消息：SystemMessage / HumanMessage / AssistantMessage / ToolMessage
- 用户画像：存储用户个人信息、病史、过敏史等，供模型参考
- 统一状态：AgentState 聚合所有状态字段，支持快照与回滚
- 短期记忆：通过 STMManager 统一管理对话历史，支持 token 感知和自动压缩

与 ChatModel 的兼容性：
- 所有消息类型都有 role 和 content 属性，可直接传给 ChatModel.invoke()
- 对话历史通过 STMManager 管理，get_messages() 方法兼容旧接口
"""

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

# 避免循环导入
if TYPE_CHECKING:
    from harness.memory.stm.stm_manager import STMManager

logger = logging.getLogger(__name__)


# ============================================================
# 消息类型体系
# ============================================================

@dataclass
class BaseMessage:
    """消息基类，所有消息类型继承此类"""
    content: str


@dataclass
class SystemMessage(BaseMessage):
    """系统消息：定义 Agent 角色和行为规范"""
    role: str = "system"


@dataclass
class HumanMessage(BaseMessage):
    """人类消息：用户的输入"""
    role: str = "user"


@dataclass
class AssistantMessage(BaseMessage):
    """助手消息：模型的回复"""
    role: str = "assistant"


@dataclass
class ToolMessage(BaseMessage):
    """
    工具消息：记录工具调用的输入和输出

    属性：
        tool_name: 被调用的工具名称
        tool_args: 传入工具的参数
    """
    role: str = "tool"
    tool_name: str = ""
    tool_args: str = ""


# ============================================================
# 用户画像
# ============================================================

@dataclass
class UserProfile:
    """
    用户画像：存储用户个人信息，供模型生成个性化回复时参考

    医疗场景下，年龄、性别、病史等信息直接影响诊断建议。
    例如：同样的血红蛋白偏低，老年人和年轻人的解读可能不同。
    """
    user_id: str                                          # 用户唯一标识
    name: str = ""                                        # 姓名
    age: int = 0                                          # 年龄
    gender: str = ""                                      # 性别："男" / "女"
    medical_history: List[str] = field(default_factory=list)     # 既往病史
    allergies: List[str] = field(default_factory=list)           # 过敏史
    current_medications: List[str] = field(default_factory=list) # 当前用药



# ============================================================
# Agent 状态
# ============================================================

@dataclass
class AgentState:
    """
    Agent 核心状态：聚合用户画像、对话历史、推理过程、任务队列等

    设计原则：
    - 单一数据源：所有状态都通过 AgentState 管理
    - 有序历史：messages 列表保留完整的时间顺序
    - 快照回滚：支持 save_snapshot() / rollback() 实现状态回溯
    - 消息过滤：提供辅助方法按类型提取消息

    使用方式：
        state = AgentState(user=UserProfile(user_id="u001"))
        state.add_message(HumanMessage(content="血红蛋白偏低怎么办？"))
        state.add_message(AssistantMessage(content="血红蛋白偏低可能..."))
    """

    # ---- 核心状态 ----
    user: UserProfile                                       # 用户画像
    system_prompt: str = ""                                 # 系统提示词（单独保存，不参与LRU淘汰）

    # ---- 推理与规划 ----
    reasoning_process: str = ""                             # 当前推理过程（模型思考链）
    task_queue: List[str] = field(default_factory=list)     # 待执行任务队列

    # ---- 记忆 ----
    memory_ref: Optional[str] = None                        # 长期记忆引用（后续对接记忆系统）
    rag_context: str = ""                                   # 当前轮 RAG 检索到的医学知识上下文
    stm: Optional["STMManager"] = None                      # 短期记忆管理器（token 感知 + 自动压缩）

    # ---- 执行控制 ----
    is_finished: bool = False                               # 本轮任务是否结束

    # ---- 快照（内部使用） ----
    _snapshots: List[dict] = field(default_factory=list, repr=False)

    # ---- 消息操作（通过 STMManager 管理） ----

    def add_message(self, message: BaseMessage):
        """添加一条消息到短期记忆"""
        if not self.stm:
            logger.warning("STMManager not initialized, message not saved")
            return

        if message.role == "system":
            # SystemMessage 单独保存到 system_prompt 字段
            self.system_prompt = message.content
            return

        self.stm.add_message(message.role, message.content)
        logger.debug("Added %s message to STM (turn %d)", message.role, self.turn_count)

    def get_messages(self) -> List[BaseMessage]:
        """获取所有消息（从 STM 重建，用于兼容旧代码）"""
        if not self.stm:
            return []

        all_msgs = self.stm.get_all_messages()
        messages = []
        for msg in all_msgs:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AssistantMessage(content=content))
            elif role == "tool":
                messages.append(ToolMessage(content=content))
            # skip system/summary messages

        return messages

    def get_last_assistant_message(self) -> Optional[AssistantMessage]:
        """获取最近一条助手回复"""
        if not self.stm:
            return None

        recent = self.stm.get_recent_messages(n=5)
        for msg in reversed(recent):
            if msg.get("role") == "assistant":
                return AssistantMessage(content=msg["content"])
        return None

    def get_last_human_message(self) -> Optional[HumanMessage]:
        """获取最近一条用户输入"""
        if not self.stm:
            return None

        recent = self.stm.get_recent_messages(n=5)
        for msg in reversed(recent):
            if msg.get("role") == "user":
                return HumanMessage(content=msg["content"])
        return None

    # ---- 消息过滤 ----

    def filter_by_type(self, msg_type: type) -> List[BaseMessage]:
        """按类型提取消息（兼容旧接口）"""
        messages = self.get_messages()
        return [m for m in messages if isinstance(m, msg_type)]

    @property
    def human_messages(self) -> List[HumanMessage]:
        """所有用户消息"""
        if not self.stm:
            return []

        all_msgs = self.stm.get_all_messages()
        return [HumanMessage(content=m["content"]) for m in all_msgs if m.get("role") == "user"]

    @property
    def assistant_messages(self) -> List[AssistantMessage]:
        """所有助手回复"""
        if not self.stm:
            return []

        all_msgs = self.stm.get_all_messages()
        return [AssistantMessage(content=m["content"]) for m in all_msgs if m.get("role") == "assistant"]

    @property
    def tool_messages(self) -> List[ToolMessage]:
        """所有工具调用记录"""
        if not self.stm:
            return []

        all_msgs = self.stm.get_all_messages()
        return [ToolMessage(content=m["content"]) for m in all_msgs if m.get("role") == "tool"]

    @property
    def turn_count(self) -> int:
        """当前对话轮次（以用户消息计数）"""
        if not self.stm:
            return 0

        all_msgs = self.stm.get_all_messages()
        return len([m for m in all_msgs if m.get("role") == "user"])

    # ---- 快照与回滚 ----

    def save_snapshot(self):
        """保存当前状态快照（深拷贝），用于后续回滚"""
        snapshot = {
            "system_prompt": self.system_prompt,
            "reasoning_process": self.reasoning_process,
            "task_queue": copy.deepcopy(self.task_queue),
            "memory_ref": self.memory_ref,
            "rag_context": self.rag_context,
            "is_finished": self.is_finished,
            # 注意：stm 不做深拷贝，因为它是共享的管理器
            # 如需回滚对话历史，应通过 stm 的 clear/re-add 机制
        }
        self._snapshots.append(snapshot)
        logger.debug("Snapshot saved (total: %d)", len(self._snapshots))

    def rollback(self) -> bool:
        """回滚到上一个快照，成功返回 True，无快照返回 False"""
        if not self._snapshots:
            logger.warning("No snapshot to rollback to")
            return False
        snapshot = self._snapshots.pop()
        self.system_prompt = snapshot.get("system_prompt", "")
        self.reasoning_process = snapshot["reasoning_process"]
        self.task_queue = snapshot["task_queue"]
        self.memory_ref = snapshot["memory_ref"]
        self.rag_context = snapshot.get("rag_context", "")
        self.is_finished = snapshot["is_finished"]
        logger.debug("Rolled back to snapshot (remaining: %d)", len(self._snapshots))
        return True

    # ---- 重置 ----

    def reset(self):
        """重置状态（保留用户画像和系统提示词）"""
        self.reasoning_process = ""
        self.task_queue = []
        self.memory_ref = None
        self.is_finished = False
        self._snapshots = []
        # 注意：system_prompt 保留，stm 也保留
        # 如需清空短期记忆，应显式调用 stm.clear()
        logger.info("State reset (system_prompt preserved)")

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        """序列化为字典（用于日志、持久化）"""
        return {
            "user": {
                "user_id": self.user.user_id,
                "name": self.user.name,
                "age": self.user.age,
                "gender": self.user.gender,
            },
            "turn_count": self.turn_count,
            "reasoning_process": self.reasoning_process,
            "task_queue": self.task_queue,
            "is_finished": self.is_finished,
            "has_system_prompt": bool(self.system_prompt),
            "has_stm": self.stm is not None,
            "stm_messages": len(self.stm.get_all_messages()) if self.stm else 0,
        }
