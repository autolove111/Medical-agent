"""
AgentLoop 调度循环：自研 while 循环替代 LangGraph 黑盒调度

核心流程（对标 Hermes Harness）：
1. 接收用户输入 → 保存快照
2. 组装 Prompt（含工具描述）
3. LLM 推理
4. 检测输出是否包含工具调用
   ├─ 是 → 执行工具 → 将结果写回上下文 → 回到步骤 2
   └─ 否 → 最终回复 → 结束循环
5. 超过最大步数 → 强制结束 + 回滚

安全机制：
- max_steps 限制（默认 5）
- 快照回滚（推理失败时恢复状态）
- loop detection（连续相同调用检测）
"""

from __future__ import annotations
import logging
from typing import Callable, Optional

from harness.llm_adapter.chat_model import ChatModel
from harness.llm_adapter.tool_parser import parse_tool_call, ToolCall
from harness.state.agent_state import (
    AgentState, HumanMessage, AssistantMessage, ToolMessage,
)
from harness.prompt.prompt_context import assemble_final_prompt

logger = logging.getLogger(__name__)


def _generate_tools_prompt(tools: list) -> str:
    """生成工具描述 Prompt 片段"""
    if not tools:
        return ""

    lines = ["\n【可用工具】你可以使用以下工具来获取信息："]
    for i, tool in enumerate(tools, 1):
        lines.append(f"{i}. {tool.name}: {tool.description}")

    lines.append(
        "\n当需要使用工具时，请用以下格式输出："
        "\n<tool_call>"
        '\n{"name": "工具名", "args": {"参数名": "参数值"}}'
        "\n</tool_call>"
        "\n工具执行结果会返回给你，然后你继续回答用户问题。"
        "\n如果不需要使用工具，正常回复即可，不要输出 <tool_call> 标签。"
    )
    return "\n".join(lines)


class AgentLoop:
    """自研 Agent 调度循环"""

    def __init__(
        self,
        chat_model: ChatModel,
        state: AgentState,
        tools: Optional[list] = None,
        max_steps: int = 5,
    ):
        self.chat_model = chat_model
        self.state = state
        self.tools = tools or []
        self.max_steps = max_steps

    def run(self, user_input: str) -> str:
        """
        执行 Agent 调度循环

        返回：最终回复文本
        """
        # Step 0: 接收输入
        self.state.add_message(HumanMessage(content=user_input))
        self.state.save_snapshot()

        call_history: list[str] = []  # 用于 loop detection

        for step in range(self.max_steps):
            logger.info("AgentLoop step %d/%d", step + 1, self.max_steps)

            # Step 1: 组装 Prompt（含工具描述）
            prompt = assemble_final_prompt(self.state)

            # 注入工具描述
            if self.tools and step < self.max_steps - 1:  # 最后一步不提供工具
                tools_text = _generate_tools_prompt(self.tools)
                prompt = prompt.replace(
                    "Assistant:",
                    f"{tools_text}\n\nAssistant:",
                )

            # Step 2: LLM 推理
            try:
                reply = self.chat_model.invoke(prompt)
            except Exception as e:
                logger.error("LLM inference failed at step %d: %s", step + 1, e)
                # 回滚并返回错误
                self.state.rollback()
                return f"抱歉，推理过程出现错误：{e}"

            # Step 3: 检测工具调用
            tool_call = parse_tool_call(reply)

            if tool_call is None:
                # 最终回复
                self.state.add_message(AssistantMessage(content=reply))
                logger.info("AgentLoop finished at step %d (no tool call)", step + 1)
                return reply

            # Step 4: 执行工具
            logger.info(
                "Tool call detected: %s args=%s",
                tool_call.name, tool_call.args,
            )

            # Loop detection
            call_sig = f"{tool_call.name}:{str(tool_call.args)}"
            if call_sig in call_history:
                logger.warning("Loop detected: %s called again", call_sig)
                # 强制终止
                self.state.add_message(AssistantMessage(
                    content="我已获取了所需信息。请提出您的问题，我会尽力为您解答。"
                ))
                return "我已获取了所需信息。请提出您的问题，我会尽力为您解答。"

            call_history.append(call_sig)

            # 查找并执行工具
            tool_result = self._execute_tool(tool_call)

            # 将工具结果写入上下文
            self.state.add_message(ToolMessage(
                content=tool_result,
                tool_name=tool_call.name,
                tool_args=str(tool_call.args),
            ))

            # 循环继续，让模型基于工具结果再推理

        # Step 5: 超过最大步数
        logger.warning("AgentLoop exceeded max steps (%d), forcing end", self.max_steps)
        self.state.rollback()
        return "抱歉，当前问题需要更多分析步骤，请尝试换个方式提问，或稍后重试。"

    def _execute_tool(self, call: ToolCall) -> str:
        """查找并执行工具"""
        for tool in self.tools:
            if tool.name == call.name:
                try:
                    # 将 args 转为 JSON 字符串传给工具函数
                    import json
                    arg_str = json.dumps(call.args, ensure_ascii=False) if call.args else "{}"
                    result = tool.func(arg_str)
                    return str(result)
                except Exception as e:
                    logger.error("Tool %s execution failed: %s", call.name, e)
                    return f"工具执行错误: {e}"

        return f"错误：未找到工具 '{call.name}'。可用工具：{[t.name for t in self.tools]}"
