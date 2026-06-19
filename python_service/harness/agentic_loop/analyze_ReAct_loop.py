"""
ReAct_loop.py
~~~~~~~~~~~~~
ReAct 循环控制器 — 驱动 LabAgent 进行 Thought → Action → Observation 多步推理

ReAct 输出格式：
    Thought: 我需要查询肌酐的参考范围
    Action: reference_lookup
    Action Input: {"indicator": "creatinine"}

    Observation: [工具返回结果]

    Thought: 根据参考范围，肌酐偏高...
    Final Answer: 您的肌酐值偏高，正常范围是...
"""

import json
import logging
import re
import time
import uuid
import asyncio
from typing import Callable, Optional, List, Dict, Any, Iterable
from enum import Enum
from contextlib import contextmanager
from harness.llm_adapter.create_agent import LabAgent

logger = logging.getLogger(__name__)


# ============================================================
# 枚举 & 数据结构
# ============================================================

class LoopStatus(Enum):
    """循环状态枚举"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_STEPS_REACHED = "max_steps_reached"
    INTERRUPTED = "interrupted"
    ERROR = "error"


# ============================================================
# ReAct Loop
# ============================================================

class analyze_ReActLoop:
    """
    ReAct 循环控制器

    驱动 LabAgent 进行 Thought → Action → Observation 多步推理。

    使用示例：
        loop = analyze_ReActLoop(max_steps=5)
        loop.on_tool_call = lambda name, args: print(f"调用工具: {name}")
        result = loop.run("患者肌酐偏高怎么办")
        print(result["answer"])

    支持上下文管理器：
        with analyze_ReActLoop(max_steps=5) as loop:
            result = loop.run("复杂任务")
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        max_steps: int = 5,
        verbose: bool = False,
        enable_safety_check: bool = True,

    ):
        """
        初始化 ReAct Loop
        """
        self.agent = LabAgent(
            user_id=user_id,
            session_id=session_id,
            def_prompt="你是一个医疗助手，分析患者的检验结果并提供建议。",
            format_prompt=(
                "请严格按照以下 ReAct 框架工作：\n\n"
                "**思考 (Thought)**：分析当前状态，决定下一步需要什么信息\n"
                "**行动 (Action)**：如果需要工具，调用相应的 function\n"
                "**观察 (Observation)**：系统会自动执行工具并返回结果\n\n"
                "**重要规则**：\n"
                "- 每次只调用一个工具\n"
                "- 获得观察结果后，继续思考下一步\n"
                "- 当信息足够时，在 final_answer 中给出最终答案\n"
                "- 思考过程用自然语言写在 content 中\n"
                "- 工具调用用 tool_calls\n\n"
                "现在开始分析："
            )
        )
        self.max_steps = max_steps
        self.verbose = verbose
        self.enable_safety_check = enable_safety_check

        # ========== 钩子函数（外部可注入） ==========
        self.on_step_start: Optional[Callable[[int, str], None]] = None
        self.on_step_end: Optional[Callable[[int, Dict[str, Any]], None]] = None
        self.on_tool_call: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_tool_result: Optional[Callable[[str, str], None]] = None
        self.on_final_answer: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[Exception, int], None]] = None

        # ========== 运行时状态 ==========
        self.status = LoopStatus.IDLE
        self.step_count = 0
        # ========== 资源管理 ==========
        # 这里可以初始化一些资源，例如数据库连接、工具实例等


    # ============================================================
    # 核心方法
    # ============================================================

    def run(self, user_query: list[str], emit: Optional[Callable] = None) -> str:
            self.step_count = 0

            if emit: emit({"type": "react_start", "query": str(user_query)})

            # 先从快照恢复历史对话，再写入新消息
            self.agent.get_short_memory_text()

            for query in user_query:
                self.agent.write_user_message_to_memory(query)
            try:
              while self.step_count < self.max_steps:
                self.step_count += 1
                if emit: emit({"type": "step_start", "step": self.step_count})
                print(f"\n🔄 ReAct 循环 - 第 {self.step_count} 步")
                print("-" * 50)
                
                # 调用模型（支持 tool_calls）
                message_prompt=self.agent.get_message_prompt()
                print(f"messages: {message_prompt}")

                response = self.agent.chat(message_prompt=message_prompt)

                # 打印完整响应日志
                print(f"\n📋 原始响应: {response}")

                assistant_message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason

                if assistant_message.tool_calls:
                    print(f"🤖 助手发出工具调用请求:")
                    if emit and assistant_message.content:
                        emit({"type": "thought", "step": self.step_count, "content": assistant_message.content})
                    # 带 tool_calls 的 assistant 消息（可能同时有 content/Thought）
                    self.agent.write_tool_calls_to_memory(
                        content=assistant_message.content or "",
                        tool_calls=[tc.model_dump() for tc in assistant_message.tool_calls],
                    )
                    # 执行所有工具调用（支持并行）
                    for tool_call in assistant_message.tool_calls:
                        # ✅ 用 try-except 包装工具执行
                        if emit:
                            try:
                                _args = json.loads(tool_call.function.arguments)
                            except Exception:
                                _args = {}
                            emit({"type": "tool_call", "step": self.step_count, "name": tool_call.function.name, "args": _args})
                        try:
                            observation = self.agent.execute_tool(
                                tool_name=tool_call.function.name,
                                arguments=json.loads(tool_call.function.arguments),
                            )
                        except Exception as e:
                            # ✅ 捕获异常，将错误信息作为观察结果
                            observation = f"工具执行失败: {type(e).__name__}: {str(e)}"
                            # 可选：打印日志便于调试
                            print(f"⚠️ 工具 {tool_call.function.name} 执行失败: {e}")
                        self.agent.write_tool_result_to_memory(tool_call.id, observation)
                        if emit: emit({"type": "observation", "step": self.step_count, "name": tool_call.function.name, "result": str(observation)[:4000]})
                    continue



                # 无 tool_calls → 纯文本回复
                if finish_reason == "stop":
                    print(f"纯文本回复，finish_reason=stop，循环结束")
                    self.agent.write_assistant_message_to_memory(assistant_message.content)
                    if emit: emit({"type": "final_answer", "content": assistant_message.content})
                    if emit: emit({"type": "react_end"})
                    return assistant_message.content
                
                # 情况3：达到长度限制
                elif finish_reason == "length":
                    print(f"长度限制回复，finish_reason=length")
                    self.agent.write_assistant_message_to_memory(assistant_message.content)
                    continue

                elif finish_reason == "content_filter":
                    print(f"内容过滤回复，finish_reason=content_filter")
                    if emit: emit({"type": "react_end"})
                    return "抱歉，无法回答这个问题"
                
                # 其他情况
                else:
                    print(f"⚠️ 未知的 finish_reason: {finish_reason}")
                    if assistant_message.content:
                        print(f"🤖 未知情况回复")
                        self.agent.write_assistant_message_to_memory(assistant_message.content)
                        if emit: emit({"type": "final_answer", "content": assistant_message.content})
                        if emit: emit({"type": "react_end"})
                        return assistant_message.content
                    else:
                        if emit: emit({"type": "react_end"})
                        return "无法生成有效回答"
            

            finally:
                # ReAct 循环结束，保存短期记忆快照
                try:
                    self.agent.memory.save_snapshot()
                    print("💾 记忆快照已保存")
                except Exception as e:
                    print(f"⚠️ 快照保存失败: {e}")

    # ============================================================
    # 钩子函数调用（内部使用）
    # ============================================================

    '''
    在适当的地方调用钩子函数，例如：
        if self.on_step_start:
            self.on_step_start(self.step_count, user_query)
        ...
        if self.on_tool_call:
            self.on_tool_call(tool_name, arguments)
        ...
        if self.on_final_answer:
            self.on_final_answer(final_answer)
    '''

    # ============================================================
    # 状态管理
    # ============================================================

    '''
    其他状态管理方法（如 interrupt, reset 等）可以在这里实现
    '''
