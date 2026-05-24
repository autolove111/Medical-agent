"""
state.agent_state
~~~~~~~~~~~~~~~~~
自研 Agent 状态管理：定义消息类型、用户画像、Agent 状态。

核心设计：
- 多态消息：SystemMessage / HumanMessage / AssistantMessage / ToolMessage
- 用户画像：存储用户个人信息、病史、过敏史等，供模型参考
- 统一状态：AgentState 聚合所有状态字段，支持快照与回滚
- 有序历史：消息按时间顺序存放在一个列表中，保留完整对话流程

与 ChatModel 的兼容性：
- 所有消息类型都有 role 和 content 属性，可直接传给 ChatModel.invoke()
"""

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

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
    messages: List[BaseMessage] = field(default_factory=list)  # 有序对话历史

    # ---- 推理与规划 ----
    reasoning_process: str = ""                             # 当前推理过程（模型思考链）
    task_queue: List[str] = field(default_factory=list)     # 待执行任务队列

    # ---- 记忆 ----
    memory_ref: Optional[str] = None                        # 长期记忆引用（后续对接记忆系统）

    # ---- 执行控制 ----
    is_finished: bool = False                               # 本轮任务是否结束

    # ---- 快照（内部使用） ----
    _snapshots: List[dict] = field(default_factory=list, repr=False)

    # ---- 消息操作 ----

    def add_message(self, message: BaseMessage):
        """添加一条消息到历史末尾"""
        self.messages.append(message)
        logger.debug("Added %s message", message.role)

    def get_messages(self) -> List[BaseMessage]:
        """获取完整消息列表（按时间顺序），可直接传给 ChatModel"""
        return self.messages

    def get_last_assistant_message(self) -> Optional[AssistantMessage]:
        """获取最近一条助手回复"""
        for msg in reversed(self.messages):
            if isinstance(msg, AssistantMessage):
                return msg
        return None

    def get_last_human_message(self) -> Optional[HumanMessage]:
        """获取最近一条用户输入"""
        for msg in reversed(self.messages):
            if isinstance(msg, HumanMessage):
                return msg
        return None

    # ---- 消息过滤 ----

    def filter_by_type(self, msg_type: type) -> List[BaseMessage]:
        """按类型提取消息"""
        return [m for m in self.messages if isinstance(m, msg_type)]

    @property
    def human_messages(self) -> List[HumanMessage]:
        """所有用户消息"""
        return self.filter_by_type(HumanMessage)

    @property
    def assistant_messages(self) -> List[AssistantMessage]:
        """所有助手回复"""
        return self.filter_by_type(AssistantMessage)

    @property
    def tool_messages(self) -> List[ToolMessage]:
        """所有工具调用记录"""
        return self.filter_by_type(ToolMessage)

    @property
    def turn_count(self) -> int:
        """当前对话轮次（以用户消息计数）"""
        return len(self.human_messages)

    # ---- 快照与回滚 ----

    def save_snapshot(self):
        """保存当前状态快照（深拷贝），用于后续回滚"""
        snapshot = {
            "messages": copy.deepcopy(self.messages),
            "reasoning_process": self.reasoning_process,
            "task_queue": copy.deepcopy(self.task_queue),
            "memory_ref": self.memory_ref,
            "is_finished": self.is_finished,
        }
        self._snapshots.append(snapshot)
        logger.debug("Snapshot saved (total: %d)", len(self._snapshots))

    def rollback(self) -> bool:
        """回滚到上一个快照，成功返回 True，无快照返回 False"""
        if not self._snapshots:
            logger.warning("No snapshot to rollback to")
            return False
        snapshot = self._snapshots.pop()
        self.messages = snapshot["messages"]
        self.reasoning_process = snapshot["reasoning_process"]
        self.task_queue = snapshot["task_queue"]
        self.memory_ref = snapshot["memory_ref"]
        self.is_finished = snapshot["is_finished"]
        logger.debug("Rolled back to snapshot (remaining: %d)", len(self._snapshots))
        return True

    # ---- 重置 ----

    def reset(self):
        """重置状态（保留用户画像和系统提示词）"""
        system_msgs = self.filter_by_type(SystemMessage)
        self.messages = system_msgs
        self.reasoning_process = ""
        self.task_queue = []
        self.memory_ref = None
        self.is_finished = False
        self._snapshots = []
        logger.info("State reset (kept %d system messages)", len(system_msgs))

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
            "message_count": len(self.messages),
            "turn_count": self.turn_count,
            "reasoning_process": self.reasoning_process,
            "task_queue": self.task_queue,
            "is_finished": self.is_finished,
        }
