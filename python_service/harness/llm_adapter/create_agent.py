"""
create_agent
~~~~~~~~~~~~
自研 Agent 创建模块。

Agent 绑定：记忆系统 + 工具注册表。
chat() 只做单次推理，工具调用循环由 loop 模块处理。
"""

import logging
from typing import Iterable

from harness.llm_adapter.chat_model import ChatModel, Chunk
from harness.memory import MemorySystem
from harness.tool import get_registry
from harness.prompt import SystemPromptBuilder
from harness.llm_adapter.chat_model import ChatModel, ChatResponse, Chunk


logger = logging.getLogger(__name__)


def _safety_check(reply: str) -> str:
    try:
        from app.safety.output_guard import get_output_guard
        guard = get_output_guard()
        report = guard.sanitize(reply)
        safe = guard.inject_disclaimer(report.sanitized)
        if report.blocked:
            logger.warning("Output blocked: %s", report.blocking_rules)
        return safe
    except Exception as e:
        logger.warning("Safety check failed: %s", e)
        return reply


# ============================================================
# LabAgent
# ============================================================

class LabAgent:
    """
    医疗检验 Agent — 绑定记忆系统 + 工具注册表

    使用方式：
        agent = LabAgent(chat_model, memory, tool_registry)
        reply = agent.chat("肌酐偏高怎么办")           # 单次推理
        reply = agent.chat_with_tools("肌酐偏高怎么办") # 带工具调用循环
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        def_prompt: str,
        format_prompt: str,
    ):

        self.memory = MemorySystem(user_id, session_id)
        self.chat_model = ChatModel()
        self.system_prompt = SystemPromptBuilder()
        self.tool_registry = get_registry()
        self.def_prompt = def_prompt
        self.format_prompt = format_prompt


    # ----------------------------------------------------------
    # 写入记忆能力
    # ----------------------------------------------------------
    def write_user_message_to_memory(self, user_input: str) -> None:
        """将用户消息写入记忆"""
        self.memory.on_user_message(user_input)

    def write_assistant_message_to_memory(self, content: str) -> None:
        """将助手回复写入记忆并保存快照"""
        self.memory.on_assistant_message(content)

    def write_tool_calls_to_memory(self, content: str, tool_calls: list[dict]) -> None:
        """将工具调用请求写入记忆"""
        self.memory.on_assistant_tool_calls(content=content, tool_calls=tool_calls)

    def write_tool_result_to_memory(self, tool_call_id: str, observation: str) -> None:
        """将工具执行结果写入记忆"""
        self.memory.on_tool_result(tool_call_id, observation)
    # ----------------------------------------------------------    
    # 获取短期记忆文本能力
    # ----------------------------------------------------------    
    def get_short_memory_text(self) -> list[dict]:
        """获取短期记忆文本，如果内存没有则从快照恢复，若快照也没有则返回空字符串"""
        short_memory = self.memory.get_short_memory_text()
        if not short_memory:
            self.memory.load_snapshot()
            short_memory = self.memory.get_short_memory_text()
        return short_memory
    

    # ----------------------------------------------------------
    # 获取summary文本能力
    # ----------------------------------------------------------
    def get_summary(self) -> list[dict]:
        """获取会话总结文本，如果内存没有则从快照恢复，若快照也没有则返回空字符串"""
        return self.memory.get_summary_text()

    # ----------------------------------------------------------
    # 获取system prompt能力
    # ----------------------------------------------------------
    def get_system_prompt(self) -> list[dict]:
        """获取系统提示词，返回 FC 格式的 system message"""
        return self.system_prompt.get(self.def_prompt, self.format_prompt, self.get_profile(), self.get_summary())

    # ----------------------------------------------------------
    # 获取患者画像文本能力  
    # ----------------------------------------------------------
    def get_profile(self) -> dict:
        """获取患者画像文本"""
        profile = self.memory.get_profile_text()
        if not profile:
            return {}
        return profile

    # ----------------------------------------------------------
    # Prompt 组装system_message+shoort memory能力，返回message列表
    # ----------------------------------------------------------
    def get_message_prompt(self) -> list[dict]:
        """组装系统提示词和短期记忆为最终 prompt，返回 FC 格式的 messages 列表"""
        messages = []
        system_message = self.get_system_prompt()
        if system_message:
            messages.extend(system_message)
        short_memory = self.get_short_memory_text()
        if short_memory:
            messages.extend(short_memory)
        return messages

    # ----------------------------------------------------------
    # 单次对话能力（不处理工具调用循环）
    # ----------------------------------------------------------
    def chat(self, message_prompt: list[dict]) -> ChatResponse:
        """单次推理，不处理工具调用循环"""

        logger.info("=" * 60)
        logger.info("PROMPT:\n%s", message_prompt)
        logger.info("=" * 60)

        tools_schemas = self.tool_registry.get_all_openai_schemas()
        response = self.chat_model.invoke(message_prompt, tools=tools_schemas)
        return response

    # ----------------------------------------------------------
    # 工具执行能力
    # --------------------------------------------------

    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """通过注册表执行工具"""
        if tool_name not in self.tool_registry:
            return f"错误：未找到工具 '{tool_name}'"
        tool = self.tool_registry.get(tool_name)
        try:
            import asyncio
            result = asyncio.run(tool.execute(**arguments))
            return result.content
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return f"工具执行错误: {e}"

    # ----------------------------------------------------------
    # 流式对话
    # ----------------------------------------------------------

    def chat_stream(self, prompt: str) -> Iterable[Chunk]:
        """流式对话（不支持工具调用）"""

        full_reply = ""
        for chunk in self.chat_model.stream(prompt):
            full_reply += chunk.content
            yield chunk

        full_reply = _safety_check(full_reply)
        self.memory.on_assistant_message(full_reply)

    # ----------------------------------------------------------
    # 会话管理
    # ----------------------------------------------------------

    def end_session(self):
        """结束会话"""
        self.memory.end_session()
