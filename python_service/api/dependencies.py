"""
FastAPI 依赖注入：AgentPool 会话池管理

核心设计：
- 每个 user_id 对应一个独立的 LabAgent 实例（完整隔离的对话状态）
- LLM 模型在首次创建 Agent 时加载（全局单例），后续用户共用推理层
- 线程安全：当前为单线程 demo 设计，生产化时需加 asyncio.Lock
"""

from __future__ import annotations
import logging
from typing import Dict, Optional

from harness.llm_adapter.create_agent import LabAgent, create_agent

logger = logging.getLogger(__name__)


class AgentPool:
    """Agent 会话池：管理多用户 LabAgent 实例"""

    def __init__(self):
        self._agents: Dict[str, LabAgent] = {}

    def get_or_create(
        self,
        user_id: str,
        user_name: str = "",
        user_age: int = 0,
        user_gender: str = "",
    ) -> LabAgent:
        """获取已有 Agent 或创建新实例（自动注册默认工具）"""
        if user_id not in self._agents:
            logger.info("Creating new agent for user=%s", user_id)
            self._agents[user_id] = create_agent(
                user_id=user_id,
                user_name=user_name,
                user_age=user_age,
                user_gender=user_gender,
            )
            # Phase 5: 自动注册默认医疗工具
            try:
                from harness.llm_adapter.agent_tools import get_default_tools
                for tool in get_default_tools():
                    self._agents[user_id].register_tool(tool)
                logger.info("Registered %d default tools for user=%s",
                            len(self._agents[user_id].tools), user_id)
            except Exception as e:
                logger.warning("Failed to register default tools: %s", e)
        return self._agents[user_id]

    def get(self, user_id: str) -> Optional[LabAgent]:
        """获取已有 Agent（不创建）"""
        return self._agents.get(user_id)

    def update_profile(self, user_id: str, name: str, age: int, gender: str) -> bool:
        """更新 Agent 的用户画像"""
        agent = self._agents.get(user_id)
        if agent is None:
            return False
        agent.state.user.name = name
        agent.state.user.age = age
        agent.state.user.gender = gender
        return True

    def remove(self, user_id: str) -> bool:
        """移除会话（释放内存）"""
        if user_id in self._agents:
            del self._agents[user_id]
            logger.info("Removed agent for user=%s", user_id)
            return True
        return False

    def reset(self, user_id: str) -> bool:
        """重置用户对话状态（保留用户画像）"""
        agent = self._agents.get(user_id)
        if agent is None:
            return False
        agent.reset()
        return True

    @property
    def user_count(self) -> int:
        return len(self._agents)


# 全局单例
_agent_pool: Optional[AgentPool] = None


def get_agent_pool() -> AgentPool:
    """获取 AgentPool 全局单例"""
    global _agent_pool
    if _agent_pool is None:
        _agent_pool = AgentPool()
    return _agent_pool
