"""
create_agent
~~~~~~~~~~~~
自研 Agent 创建模块：利用 harness 层的 ModelLoader + ChatModel 构建基础 Agent。

核心职责：
- 初始化模型（从 .env 读取路径，自动选择量化方案）
- 通过 AgentState 管理对话状态
- 通过 prompt_context 构建提示词
- 提供同步 / 流式两种调用方式
- 预留工具调用接口，后续扩展
- 接入 RAG 医学知识检索
"""

import os
import sys
import logging
from dataclasses import dataclass
from typing import List, Optional, Callable, Iterable

from dotenv import load_dotenv

from harness.llm_core.model_loader import ModelLoader, ModelConfig
from harness.llm_adapter.chat_model import ChatModel, Chunk
from harness.state.agent_state import (
    AgentState,
    UserProfile,
    SystemMessage,
    HumanMessage,
    AssistantMessage,
)
from harness.prompt.prompt_context import build_system_prompt, assemble_final_prompt

logger = logging.getLogger(__name__)

# .env 所在目录（python_service/），用于解析相对路径
_ENV_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(_ENV_DIR, ".env"))

# ---- RAG 模块（可选） ----
_rag_retrieve = None


def _ensure_rag():
    """延迟加载 RAG 检索函数，避免模型加载阶段导入失败阻塞主流程"""
    global _rag_retrieve
    if _rag_retrieve is not None:
        return _rag_retrieve

    _long_memory = os.path.join(_ENV_DIR, "harness", "long_memory")
    if _long_memory not in sys.path:
        sys.path.insert(0, _long_memory)

    try:
        from knowledge.rag import retrieve_medical_knowledge
        _rag_retrieve = retrieve_medical_knowledge
        logger.info("RAG module loaded successfully")
    except Exception as e:
        logger.warning("RAG module unavailable: %s", e)
        _rag_retrieve = False
    return _rag_retrieve


@dataclass
class Tool:
    """
    工具定义（预留接口，后续第四步自研工具引擎时扩展）

    属性：
        name:        工具名称，用于模型识别和调用
        description: 工具描述，写入 prompt 让模型理解何时调用
        func:        实际执行函数，接收字符串参数，返回字符串结果
    """
    name: str
    description: str
    func: Callable[[str], str]


class LabAgent:
    """
    医疗检验 Agent

    使用方式：
        agent = create_agent(user_id="u001")
        reply = agent.chat("血红蛋白偏低是什么意思？")
        for chunk in agent.chat_stream("继续解释"): ...

    状态管理：
        agent.state              # AgentState 实例
        agent.state.user         # 用户画像
        agent.state.messages     # 有序对话历史
        agent.state.turn_count   # 当前轮次
    """

    def __init__(
        self,
        chat_model: ChatModel,
        state: AgentState,
        tools: Optional[List[Tool]] = None,
    ):
        self.chat_model = chat_model
        self.state = state
        self.tools: List[Tool] = tools or []

    def reset(self):
        """重置状态（保留用户画像和 system prompt）"""
        self.state.reset()

    def _do_rag(self, query: str):
        """执行 RAG 检索并将结果写入 state.rag_context"""
        rag_fn = _ensure_rag()
        if not rag_fn:
            self.state.rag_context = ""
            return
        try:
            answer, docs = rag_fn(query)
            if answer:
                self.state.rag_context = answer
                logger.info("RAG hit: %d chars, %d docs", len(answer), len(docs))
            else:
                self.state.rag_context = ""
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            self.state.rag_context = ""

    def _safety_check(self, reply: str) -> str:
        """Phase 6: 安全红线检查 + 免责声明注入"""
        try:
            from app.safety.output_guard import get_output_guard
            guard = get_output_guard()
            report = guard.sanitize(reply)
            safe = guard.inject_disclaimer(report.sanitized)
            if report.blocked:
                logger.warning("Output blocked by safety rules: %s", report.blocking_rules)
            elif report.warnings:
                logger.info("Output warnings: %s", report.warnings)
            return safe
        except Exception as e:
            logger.warning("Safety check failed (output passed through): %s", e)
            return reply

    def chat(self, user_input: str) -> str:
        """同步对话：发送用户输入，返回完整回复"""
        self.state.add_message(HumanMessage(content=user_input))

        # RAG 检索医学知识库
        self._do_rag(user_input)

        # 从 state 组装四层 prompt，传给 ChatModel
        prompt = assemble_final_prompt(self.state)
        reply = self.chat_model.invoke(prompt)

        # Phase 6: 安全红线 + 免责声明
        reply = self._safety_check(reply)

        self.state.add_message(AssistantMessage(content=reply))
        return reply

    def chat_stream(self, user_input: str) -> Iterable[Chunk]:
        """流式对话：逐 token 返回回复片段"""
        self.state.add_message(HumanMessage(content=user_input))

        # RAG 检索医学知识库
        self._do_rag(user_input)

        # 从 state 组装四层 prompt，传给 ChatModel
        prompt = assemble_final_prompt(self.state)

        full_reply = ""
        for chunk in self.chat_model.stream(prompt):
            full_reply += chunk.content
            yield chunk

        # Phase 6: 安全红线 + 免责声明（对完整回复执行）
        full_reply = self._safety_check(full_reply)

        self.state.add_message(AssistantMessage(content=full_reply))

    def call_tool(self, tool_name: str, args: str) -> str:
        """工具调用：根据名称查找并执行工具"""
        for tool in self.tools:
            if tool.name == tool_name:
                logger.info("Calling tool: %s", tool_name)
                return tool.func(args)
        return f"Error: tool '{tool_name}' not found"

    def register_tool(self, tool: Tool):
        """注册新工具"""
        self.tools.append(tool)
        logger.info("Registered tool: %s", tool.name)

    def agent_loop(self, user_input: str, max_steps: int = 5) -> str:
        """
        Agent 自主调度循环（Phase 5）

        与 chat() 的区别：
        - chat():     单次推理，简单问答
        - agent_loop(): 多步推理，支持工具调用链

        流程：输入 → 推理 → 检测工具调用 → 执行工具 → 再推理 → ... → 最终回复
        """
        from harness.llm_adapter.agent_loop import AgentLoop

        loop = AgentLoop(
            chat_model=self.chat_model,
            state=self.state,
            tools=self.tools if self.tools else None,
            max_steps=max_steps,
        )
        return loop.run(user_input)


def create_agent(
    user_id: str = "default",
    model_path: Optional[str] = None,
    system_prompt: str = "",
    use_4bit: bool = True,
    temperature: float = 0.7,
    max_new_tokens: int = 2000,
    tools: Optional[List[Tool]] = None,
    user_name: str = "",
    user_age: int = 0,
    user_gender: str = "",
) -> LabAgent:
    """
    Agent 工厂函数：一行代码创建完整的 LabAgent

    使用示例：
        agent = create_agent(user_id="u001", user_name="张三", user_age=45)
        reply = agent.chat("血红蛋白偏低怎么办？")
    """
    # Step 1: 确定模型路径（相对路径基于 python_service 目录解析）
    if model_path is None:
        raw_path = os.getenv("LLM_MODEL_PATH")
        if raw_path:
            # 相对路径基于 .env 所在目录（python_service/）解析
            if not os.path.isabs(raw_path):
                model_path = os.path.normpath(os.path.join(_ENV_DIR, raw_path))
            else:
                model_path = raw_path
        else:
            model_path = os.path.normpath(
                os.path.join(_ENV_DIR, "..", "..", "models", "Qwen2.5-7B-Instruct")
            )

    # Step 2: 创建用户画像
    user = UserProfile(
        user_id=user_id,
        name=user_name,
        age=user_age,
        gender=user_gender,
    )

    # Step 3: 构建 system prompt（通过 prompt_context 模块）
    full_system_prompt = build_system_prompt(user, system_prompt)

    # Step 4: 初始化模型（单例，全局只加载一次）
    config = ModelConfig(
        model_path=model_path,
        use_4bit=use_4bit,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
    )
    loader = ModelLoader.init(config)
    chat_model = ChatModel(loader)

    # Step 5: 创建状态并写入 system prompt
    state = AgentState(user=user)
    state.add_message(SystemMessage(content=full_system_prompt))

    # Step 6: 组装 Agent
    agent = LabAgent(chat_model=chat_model, state=state, tools=tools)

    logger.info("Agent created | user=%s model=%s", user_id, model_path)
    return agent
