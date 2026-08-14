"""
Loop Worker：纯调度器

支持两种执行模式：
  - ReAct：聊天模式，想一步做一步
  - Plan：报告模式，先规划再逐步执行

启动方式：
    cd backend
    python -m app.worker.loop_worker
"""

import json
import logging
import sys
import os
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Loop-Worker] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("loop_worker")

# 路径设置
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DIR = os.path.dirname(_APP_DIR)
_AI_DIR = os.path.join(_PROJECT_DIR, "..", "ai-services")

for _p in [_APP_DIR, _AI_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from broker.interface import MessageBroker


# ============================================================
# TaskState：任务状态存 Redis Hash（medlab:task:chat:{task_id}）
# ============================================================

class TaskState:
    """任务执行状态，存到 task Redis Hash，不污染 STM。"""

    def __init__(self, task_id: str, broker: MessageBroker):
        self._task_id = task_id
        self._broker = broker
        self._cache = {}  # 本地缓存，减少 Redis 读取
        self._stm = None  # 绑定的 STM 实例

    def _get(self, key: str, default=""):
        if key in self._cache:
            return self._cache[key]
        data = self._broker.get_task_status(self._task_id, task_type="chat")
        val = (data or {}).get(key, default)
        self._cache[key] = val
        return val

    def _set(self, **kwargs):
        self._cache.update(kwargs)
        self._broker.update_task_status(self._task_id, self._get("status", "running"),
                                         task_type="chat", **kwargs)

    @property
    def status(self) -> str:
        return self._get("status", "")

    @status.setter
    def status(self, value: str):
        self._cache["status"] = value
        self._broker.update_task_status(self._task_id, value, task_type="chat")

    @property
    def mode(self) -> str:
        return self._get("mode", "react")

    @mode.setter
    def mode(self, value: str):
        self._set(mode=value)

    @property
    def step(self) -> int:
        val = self._get("step", "0")
        return int(val) if val else 0

    @step.setter
    def step(self, value: int):
        self._set(step=str(value))

    @property
    def plan(self) -> str:
        return self._get("plan", "")

    @plan.setter
    def plan(self, value: str):
        self._set(plan=value)

    @property
    def pending_tool_call(self) -> dict:
        val = self._get("pending_tool_call", "{}")
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return {}
        return val if isinstance(val, dict) else {}

    @pending_tool_call.setter
    def pending_tool_call(self, value: dict):
        self._set(pending_tool_call=json.dumps(value, ensure_ascii=False))

    @property
    def messages(self) -> list:
        """从 STM 读取消息（对话上下文）。"""
        return self._stm.messages if self._stm else []

    def bind_stm(self, stm):
        """绑定 STM，用于读取消息。"""
        self._stm = stm

    @property
    def tool_call_count(self) -> int:
        val = self._get("tool_call_count", "0")
        return int(val) if val else 0

    @tool_call_count.setter
    def tool_call_count(self, value: int):
        self._set(tool_call_count=str(value))


# ============================================================
# 辅助函数
# ============================================================

def _get_memory(user_id: str, session_id: str, load_snapshot: bool = False):
    """获取记忆系统实例。

    load_snapshot=True 时，仅当 Redis 消息为空才加载快照（避免覆盖当前会话消息）。
    """
    from memory import MemorySystem
    memory = MemorySystem(user_id, session_id)
    if load_snapshot and not memory._stm.messages:
        memory.load_snapshot()
    return memory


def _get_tools() -> list:
    try:
        from tools import get_registry
        registry = get_registry()
        return registry.get_all_openai_schemas()
    except Exception as exc:
        logger.warning("Failed to get tools: %s", exc)
        return []


def _execute_tool(tool_name: str, args: dict) -> str:
    try:
        from tools import get_registry
        registry = get_registry()
        if tool_name not in registry:
            return f"工具 {tool_name} 未找到"
        tool = registry.get(tool_name)
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(tool.execute(**args))
        return result.content if hasattr(result, "content") else str(result)
    except Exception as exc:
        return f"工具执行失败: {exc}"


def _get_stm(user_id: str, session_id: str):
    from memory.short_memory.store import ShortMemoryStore
    return ShortMemoryStore(user_id=user_id, session_id=session_id)


def _get_task_state(task_id: str, broker: MessageBroker) -> TaskState:
    """获取任务状态对象。"""
    return TaskState(task_id, broker)


def _get_current_query(stm_messages: list) -> str:
    """从消息列表中获取当前用户问题（最后一条用户消息）。"""
    for msg in reversed(stm_messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _format_stm_messages(stm_messages: list) -> str:
    """格式化短期记忆消息为文本，用于注入到 Prompt 中。

    Args:
        stm_messages: 短期记忆中的消息列表

    Returns:
        格式化后的文本
    """
    if not stm_messages:
        return ""

    lines = []
    for msg in stm_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            lines.append(f"用户：{content}")
        elif role == "assistant":
            # 如果有 tool_calls，显示工具调用
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    func_name = tc.get("function", {}).get("name", "")
                    lines.append(f"助手：[调用工具 {func_name}]")
            else:
                lines.append(f"助手：{content}")
        elif role == "tool":
            # 工具结果，简短显示
            lines.append(f"[工具结果：{content[:100]}...]")

    return "\n".join(lines)


def _build_messages(template_id: str, stm_messages: list, **variables) -> list:
    """拼接系统指令和对话历史。

    Args:
        template_id: 模板 ID（如 "chat", "report/plan"）
        stm_messages: 短期记忆中的对话历史
        **variables: 模板变量

    Returns:
        完整的 messages 列表
    """
    from prompts import load_prompt

    # 1. 提取当前用户的问题（最后一条用户消息）
    #    如果调用方已通过 **variables 传入 query，则优先使用
    query = variables.pop("query", "")
    history_messages = stm_messages
    if not query and stm_messages and stm_messages[-1].get("role") == "user":
        query = stm_messages[-1].get("content", "")
        history_messages = stm_messages[:-1]  # 不包含当前问题

    # 调试日志
    logger.info("🔍 _build_messages | stm_count=%d query=%s history_count=%d",
                len(stm_messages), query[:80] if query else "(empty)", len(history_messages))

    # 2. 格式化历史消息
    formatted_messages = _format_stm_messages(history_messages)

    # 3. 加载 Prompt 模板（注入历史消息和当前问题）
    messages = load_prompt(template_id, messages=formatted_messages, query=query, **variables)

    return messages


# ============================================================
# 新任务入口
# ============================================================

def on_new_task(task: dict, broker: MessageBroker):
    task_id = task["task_id"]
    user_id = task["user_id"]
    session_id = task["session_id"]
    query = task["query"]
    task_type = task.get("task_type", "chat")

    logger.info("▶ New task | task_id=%s type=%s user=%s query=%s",
                task_id, task_type, user_id, query[:50])

    broker.update_task_status(task_id, "running", task_type="chat")

    # 初始化 STM（只存对话）和 TaskState（存执行状态）
    stm = _get_stm(user_id, session_id)
    ts = _get_task_state(task_id, broker)
    ts.bind_stm(stm)

    # 将用户消息写入 STM
    if query:
        try:
            stm.add_user_message(query)
            logger.info("✓ Query saved to STM | user=%s session=%s query=%s msgs_after=%d",
                        user_id, session_id, query[:80], len(stm.messages))
        except Exception as e:
            logger.error("✗ Failed to save query to STM | user=%s session=%s error=%s",
                        user_id, session_id, e, exc_info=True)
    else:
        logger.warning("⚠ Query is empty, skipping STM write | user=%s session=%s", user_id, session_id)

    if task_type == "report":
        _start_plan(task_id, user_id, session_id, ts, broker)
    else:
        _start_react(task_id, user_id, session_id, ts, broker)


# ============================================================
# ReAct 模式（聊天）
# ============================================================

def _start_react(task_id, user_id, session_id, ts, broker):
    """ReAct：直接提交给 LLM，让它决定下一步。"""
    ts.mode = "react"
    ts.step = 1
    ts.status = "waiting_llm"
    ts.tool_call_count = 0  # 初始化工具调用计数器

    tools = _get_tools()
    stm_msgs = ts.messages
    logger.info("🔍 _start_react | task_id=%s stm_msgs=%d last_msg=%s",
                task_id, len(stm_msgs),
                (stm_msgs[-1].get("content", "")[:80] if stm_msgs else "(empty)"))
    messages = _build_messages("chat", stm_msgs)
    broker.submit_llm_request(task_id, messages, tools)
    broker.publish_stream_chunk(task_id, "step_start", {"step": 1, "mode": "react"})


def _react_on_llm(msg, task_id, user_id, session_id, ts, broker):
    """ReAct 收到 LLM 结果。"""
    content = msg.get("content", "")
    reasoning_content = msg.get("reasoning_content")
    tool_calls = msg.get("tool_calls")
    step = ts.step

    if content or reasoning_content:
        broker.publish_stream_chunk(task_id, "thought", {
            "step": step,
            "thinking": reasoning_content,
            "content": content,
        })

    if tool_calls:
        ts.tool_call_count = ts.tool_call_count + 1

        # 工具调用次数限制：超过 3 次不传 tools，强制 LLM 给结论
        if ts.tool_call_count > 3:
            logger.warning("Tool call limit reached | task_id=%s count=%d", task_id, ts.tool_call_count)
            memory = _get_memory(user_id, session_id)
            memory.on_assistant_message(content or "")
            broker.submit_llm_request(task_id, _build_messages("chat", ts.messages, query=_get_current_query(ts.messages)))  # 不传 tools
            return

        # 只处理第一个 tool_call（避免多个 tool_call 但只有部分有 result）
        tc = tool_calls[0]
        func_name = tc["function"]["name"]
        func_args = json.loads(tc["function"]["arguments"])

        memory = _get_memory(user_id, session_id)
        memory.on_assistant_tool_calls(content, [tc], reasoning_content=reasoning_content)

        logger.info("Tool call | task_id=%s tool=%s count=%d", task_id, func_name, ts.tool_call_count)
        broker.publish_stream_chunk(task_id, "tool_call", {"name": func_name, "args": func_args})

        if func_name == "search_knowledge":
            ts.status = "waiting_rag"
            ts.pending_tool_call = tc
            broker.submit_rag_request(task_id, func_args.get("query", ""))
        else:
            result = _execute_tool(func_name, func_args)
            memory = _get_memory(user_id, session_id)
            memory.on_tool_result(tc["id"], result)
            broker.publish_stream_chunk(task_id, "tool_result", {"name": func_name, "result": result[:1000]})

            ts.step = step + 1
            ts.status = "waiting_llm"
            broker.submit_llm_request(task_id, _build_messages("chat", ts.messages, query=_get_current_query(ts.messages)), _get_tools())
    else:
        # 最终回答
        memory = _get_memory(user_id, session_id)
        memory.on_assistant_message(content, reasoning_content=reasoning_content)
        _finish_task(task_id, user_id, session_id, broker=broker, answer=content)


def _react_on_rag(msg, task_id, user_id, session_id, ts, broker):
    """ReAct 收到 RAG 结果。"""
    results = msg.get("results", [])
    error = msg.get("error", "")
    step = ts.step
    pending_tc = ts.pending_tool_call

    if error:
        answer = f"RAG 检索失败: {error}"
    elif not results:
        answer = "未找到相关医学知识。"
    else:
        answer = "\n\n".join(
            f"【来源】{r.get('metadata', {}).get('source', 'unknown')}\n{r['content']}"
            for r in results
        )

    memory = _get_memory(user_id, session_id)
    memory.on_tool_result(pending_tc.get("id", ""), answer)
    broker.publish_stream_chunk(task_id, "tool_result", {"name": "search_knowledge", "result": answer[:1000]})

    ts.step = step + 1
    ts.status = "waiting_llm"

    # 工具调用次数限制：超过 3 次不传 tools，强制 LLM 给结论
    if ts.tool_call_count > 3:
        logger.warning("Tool call limit reached (RAG) | task_id=%s count=%d", task_id, ts.tool_call_count)
        broker.submit_llm_request(task_id, _build_messages("chat", ts.messages, query=_get_current_query(ts.messages)))  # 不传 tools
    else:
        broker.submit_llm_request(task_id, _build_messages("chat", ts.messages, query=_get_current_query(ts.messages)), _get_tools())


# ============================================================
# Plan 模式（报告解读）
# ============================================================

PLAN_SYSTEM_PROMPT = """你是医疗报告分析助手。请为用户的报告解读任务制定分析计划。

返回一个 JSON 数组，每个元素是一个分析步骤。
步骤数量 2-5 个，每个步骤描述一个需要完成的分析任务。

示例返回：
["搜索肌酐偏高的临床意义和可能原因", "搜索血糖偏高的临床意义", "分析肌酐和血糖异常的关联性", "综合以上分析生成报告解读"]

只返回 JSON 数组，不要有其他内容。"""


def _start_plan(task_id, user_id, session_id, ts, broker):
    """Plan：先让 LLM 生成计划。"""
    ts.mode = "plan"
    ts.step = 0
    ts.status = "planning"
    ts.plan = ""


    messages = _build_messages("report/plan", ts.messages)

    broker.submit_llm_request(task_id, messages)
    broker.publish_stream_chunk(task_id, "step_start", {"step": 0, "mode": "plan"})


def _plan_on_llm(msg, task_id, user_id, session_id, ts, broker):
    """Plan 收到 LLM 结果。根据 status 分发。"""
    status = ts.status
    content = msg.get("content", "")
    reasoning_content = msg.get("reasoning_content")
    tool_calls = msg.get("tool_calls")

    if status == "planning":
        _plan_handle_plan(task_id, user_id, session_id, ts, broker, content, reasoning_content)
    elif status.startswith("step_"):
        _plan_handle_step(task_id, user_id, session_id, ts, broker, content, tool_calls, reasoning_content)
    elif status == "synthesizing":
        _plan_handle_synthesize(task_id, user_id, session_id, ts, broker, content, reasoning_content)


def _plan_handle_plan(task_id, user_id, session_id, ts, broker, content, reasoning_content=None):
    """收到计划，开始执行第一步。"""
    try:
        plan = json.loads(content)
        if not isinstance(plan, list) or len(plan) == 0:
            raise ValueError("计划不是数组")
    except Exception:
        # LLM 没返回有效计划，降级为 ReAct
        logger.warning("Plan parse failed, fallback to react | task_id=%s", task_id)
        ts.mode = "react"
        ts.step = 1
        ts.status = "waiting_llm"
        broker.submit_llm_request(task_id, _build_messages("chat", ts.messages, query=_get_current_query(ts.messages)), _get_tools())
        return

    ts.plan = json.dumps(plan, ensure_ascii=False)
    ts.step = 0
    ts.status = "step_0"

    logger.info("Plan created | task_id=%s steps=%d", task_id, len(plan))
    broker.publish_stream_chunk(task_id, "plan", {"steps": plan})

    # 写入计划到记忆
    memory = _get_memory(user_id, session_id)
    memory.on_assistant_message(f"分析计划：{json.dumps(plan, ensure_ascii=False)}", reasoning_content=reasoning_content)

    # 执行第一步（重置工具调用计数器）
    ts.tool_call_count = 0
    _plan_execute_step(task_id, user_id, session_id, ts, broker, 0, plan)


def _plan_execute_step(task_id, user_id, session_id, ts, broker, step_idx, plan):
    """执行计划中的一步。"""
    step_desc = plan[step_idx]
    # 不在这里重置 tool_call_count，由调用方负责重置

    broker.publish_stream_chunk(task_id, "plan_step_start", {"step": step_idx, "description": step_desc})

    # 读取化验单内容（从任务状态）
    report_data = ""
    try:
        task_info = broker.get_task_status(task_id, task_type="chat")
        if task_info and "raw_markdown" in task_info:
            report_data = task_info["raw_markdown"]
    except Exception:
        pass

    messages = _build_messages("report/execute", ts.messages,
        step_idx=step_idx + 1,
        total_steps=len(plan),
        step_desc=step_desc,
        report=report_data,
    )

    broker.submit_llm_request(task_id, messages, _get_tools())


def _plan_handle_step(task_id, user_id, session_id, ts, broker, content, tool_calls, reasoning_content=None):
    """执行步骤中收到 LLM 结果。可能有工具调用，也可能直接给出结论。"""
    plan = json.loads(ts.plan) if ts.plan else []
    step_idx = int(ts.status.split("_")[1])

    if content:
        broker.publish_stream_chunk(task_id, "plan_step_thought", {"step": step_idx, "content": content})

    if tool_calls:
        ts.tool_call_count = ts.tool_call_count + 1

        # 工具调用次数限制：超过 3 次不传 tools，强制 LLM 给结论
        if ts.tool_call_count > 3:
            logger.warning("Tool call limit reached | task_id=%s step=%d", task_id, step_idx)
            memory = _get_memory(user_id, session_id)
            memory.on_assistant_message(content or "")
            messages = _build_messages("report/execute", ts.messages,
                step_idx=step_idx + 1, total_steps=len(plan), step_desc=plan[step_idx],
                report=task_info.get("raw_markdown", "") if (task_info := broker.get_task_status(task_id, task_type="chat")) else "",
            )
            broker.submit_llm_request(task_id, messages)  # 不传 tools
            return

        # 只处理第一个 tool_call
        tc = tool_calls[0]
        func_name = tc["function"]["name"]
        func_args = json.loads(tc["function"]["arguments"])

        memory = _get_memory(user_id, session_id)
        memory.on_assistant_tool_calls(content, [tc], reasoning_content=reasoning_content)

        broker.publish_stream_chunk(task_id, "tool_call", {"name": func_name, "args": func_args})

        if func_name == "search_knowledge":
            ts.status = f"step_{step_idx}"  # 保持当前步骤
            ts.pending_tool_call = tc
            broker.submit_rag_request(task_id, func_args.get("query", ""))
        else:
            result = _execute_tool(func_name, func_args)
            memory = _get_memory(user_id, session_id)
            memory.on_tool_result(tc["id"], result)
            broker.publish_stream_chunk(task_id, "tool_result", {"name": func_name, "result": result[:1000]})
            # 再次提交当前步骤
            _plan_execute_step(task_id, user_id, session_id, ts, broker, step_idx, plan)
    else:
        # 步骤完成，存入记忆
        memory = _get_memory(user_id, session_id)
        memory.on_assistant_message(content, reasoning_content=reasoning_content)

        broker.publish_stream_chunk(task_id, "plan_step_done", {"step": step_idx, "result": content[:500]})

        # 下一步
        if step_idx + 1 < len(plan):
            ts.step = step_idx + 1
            ts.status = f"step_{step_idx + 1}"
            ts.tool_call_count = 0  # 重置工具调用计数器
            _plan_execute_step(task_id, user_id, session_id, ts, broker, step_idx + 1, plan)
        else:
            # 所有步骤完成 → 综合
            _plan_start_synthesis(task_id, user_id, session_id, ts, broker)


def _plan_on_rag(msg, task_id, user_id, session_id, ts, broker):
    """Plan 执行步骤中收到 RAG 结果。"""
    results = msg.get("results", [])
    error = msg.get("error", "")
    pending_tc = ts.pending_tool_call
    plan = json.loads(ts.plan) if ts.plan else []
    step_idx = int(ts.status.split("_")[1]) if ts.status.startswith("step_") else 0

    if error:
        answer = f"RAG 检索失败: {error}"
    elif not results:
        answer = "未找到相关医学知识。"
    else:
        answer = "\n\n".join(
            f"【来源】{r.get('metadata', {}).get('source', 'unknown')}\n{r['content']}"
            for r in results
        )

    memory = _get_memory(user_id, session_id)
    memory.on_tool_result(pending_tc.get("id", ""), answer)
    broker.publish_stream_chunk(task_id, "tool_result", {"name": "search_knowledge", "result": answer[:1000]})

    # 再次提交当前步骤（让 LLM 基于 RAG 结果生成结论）
    _plan_execute_step(task_id, user_id, session_id, ts, broker, step_idx, plan)


def _plan_start_synthesis(task_id, user_id, session_id, ts, broker):
    """所有步骤完成，开始综合生成最终回答。"""
    ts.status = "synthesizing"

    broker.publish_stream_chunk(task_id, "plan_synthesis_start", {})

    # 读取化验单内容（从任务状态）
    report_data = ""
    try:
        task_info = broker.get_task_status(task_id, task_type="chat")
        if task_info and "raw_markdown" in task_info:
            report_data = task_info["raw_markdown"]
    except Exception:
        pass

    messages = _build_messages("report/synthesize", ts.messages, report=report_data)

    broker.submit_llm_request(task_id, messages)


def _plan_handle_synthesize(task_id, user_id, session_id, ts, broker, content, reasoning_content=None):
    """综合步骤完成，生成最终回答。"""
    memory = _get_memory(user_id, session_id)
    memory.on_assistant_message(content, reasoning_content=reasoning_content)

    # ---- 生成推荐问题 ----
    try:
        from question_gen.question_generator import generate_report_questions
        stm = _get_stm(user_id, session_id)
        questions = generate_report_questions(stm.messages)
        if questions:
            broker.publish_stream_chunk(task_id, "suggested_questions", {"questions": questions})
            logger.info("✓ Suggested questions | task_id=%s count=%d", task_id, len(questions))
    except Exception as e:
        logger.warning("Suggested questions failed | task_id=%s: %s", task_id, e)
    # ---- 推荐问题结束 ----

    _finish_task(task_id, user_id, session_id, broker=broker, answer=content)


# ============================================================
# 统一入口（根据 mode 分发）
# ============================================================

def on_llm_result(msg: dict, broker: MessageBroker):
    task_id = msg["task_id"]
    finish_reason = msg.get("finish_reason", "")

    task_info = broker.get_task_status(task_id, task_type="chat")
    if not task_info:
        logger.warning("Task info not found | task_id=%s", task_id)
        return

    user_id = task_info.get("user_id", "")
    session_id = task_info.get("session_id", "")
    ts = _get_task_state(task_id, broker)
    ts.bind_stm(_get_stm(user_id, session_id))

    if finish_reason == "error":
        error = msg.get("error", "LLM 调用失败")
        logger.error("LLM error | task_id=%s error=%s", task_id, error)
        _finish_task(task_id, user_id, session_id, broker=broker, error=error)
        return

    mode = ts.mode

    if mode == "plan":
        _plan_on_llm(msg, task_id, user_id, session_id, ts, broker)
    else:
        _react_on_llm(msg, task_id, user_id, session_id, ts, broker)


def on_rag_result(msg: dict, broker: MessageBroker):
    task_id = msg["task_id"]

    task_info = broker.get_task_status(task_id, task_type="chat")
    if not task_info:
        logger.warning("Task info not found | task_id=%s", task_id)
        return

    user_id = task_info.get("user_id", "")
    session_id = task_info.get("session_id", "")
    ts = _get_task_state(task_id, broker)
    ts.bind_stm(_get_stm(user_id, session_id))

    mode = ts.mode

    if mode == "plan":
        _plan_on_rag(msg, task_id, user_id, session_id, ts, broker)
    else:
        _react_on_rag(msg, task_id, user_id, session_id, ts, broker)


# ============================================================
# 任务结束
# ============================================================

def _finish_task(task_id, user_id, session_id, broker=None, answer="", error=""):
    if answer:
        broker.publish_stream_chunk(task_id, "final_answer", {"answer": answer})
        broker.update_task_status(task_id, "completed", task_type="chat", result=answer)
    else:
        broker.publish_stream_chunk(task_id, "task_result", {"status": "failed", "error": error})
        broker.update_task_status(task_id, "failed", task_type="chat", error=error)

    # 刷新缓冲到 PostgreSQL + 保存快照
    try:
        memory = _get_memory(user_id, session_id)
        memory.end_session()
        logger.info("Memory flushed & snapshot saved | task_id=%s", task_id)
    except Exception as e:
        logger.error("Memory flush failed | task_id=%s error=%s", task_id, e)

    # 不需要清理 task 状态，TTL 会自动过期
    logger.info("✓ Task finished | task_id=%s", task_id)


# ============================================================
# 主循环
# ============================================================

def main(broker: MessageBroker = None):
    if broker is None:
        from broker.redis_impl import RedisBroker
        broker = RedisBroker()

    logger.info("=" * 50)
    logger.info("Loop Worker (Dispatcher) started")
    logger.info("=" * 50)

    while True:
        try:
            source, msg = broker.pop_any(timeout=5)

            if source == "task" and msg:
                on_new_task(msg, broker)
            elif source == "llm_result" and msg:
                on_llm_result(msg, broker)
            elif source == "rag_result" and msg:
                on_rag_result(msg, broker)

        except KeyboardInterrupt:
            logger.info("Loop Worker interrupted")
            break
        except Exception as exc:
            logger.error("Loop Worker error: %s", exc, exc_info=True)
            time.sleep(0.1)


if __name__ == "__main__":
    main()
