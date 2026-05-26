"""
prompt.prompt_context
~~~~~~~~~~~~~~~~~~~~~
提示词上下文构建：按四层架构组装最终 prompt。

四层架构：
1. 系统基底 Prompt：身份、全局规则、禁忌约束（全局不变）
2. 任务指令 Prompt：当前要做的核心事情
3. 上下文 Prompt：历史对话、工具结果、任务状态（动态变化）
4. 格式 FewShot Prompt：输出样式、参考示例、截断规则

职责：
- 用户画像 -> 文本（供系统基底层参考）
- 消息列表 -> 上下文层文本
- 四层组装 -> 最终 prompt
"""

from typing import List

from harness.state.agent_state import UserProfile, BaseMessage, AgentState


# ============================================================
# 用户画像转文本
# ============================================================

def user_to_prompt_text(user: UserProfile) -> str:
    """
    将用户画像转为文本，供系统基底 Prompt 使用

    示例输出：
        用户ID: u001 | 姓名: 张三 | 年龄: 45岁 | 性别: 男 | 既往病史: 糖尿病, 高血压
    """
    parts = [f"用户ID: {user.user_id}"]
    if user.name:
        parts.append(f"姓名: {user.name}")
    if user.age > 0:
        parts.append(f"年龄: {user.age}岁")
    if user.gender:
        parts.append(f"性别: {user.gender}")
    if user.medical_history:
        parts.append(f"既往病史: {', '.join(user.medical_history)}")
    if user.allergies:
        parts.append(f"过敏史: {', '.join(user.allergies)}")
    if user.current_medications:
        parts.append(f"当前用药: {', '.join(user.current_medications)}")
    return " | ".join(parts)


# ============================================================
# 第一层：系统基底 Prompt（身份、规则、禁忌）
# ============================================================

DEFAULT_SYSTEM_PROMPT = (
    "你是一个专业的医疗检验助手，擅长解读化验报告、分析检验指标异常原因、"
    "给出专业的医学建议。请用准确、专业但易懂的语言回答用户问题。"
)


def build_system_prompt(user: UserProfile, custom_prompt: str = "") -> str:
    """
    构建第一层：系统基底 Prompt

    包含：身份定义 + 全局规则 + 用户画像
    """
    prompt = custom_prompt if custom_prompt else DEFAULT_SYSTEM_PROMPT

    user_info = user_to_prompt_text(user)
    if user_info:
        prompt += f"\n\n当前用户信息：{user_info}"

    return prompt


# ============================================================
# 第二层：任务指令 Prompt（当前要做什么）
# ============================================================

DEFAULT_TASK_INSTRUCTION = (
    "请根据用户的问题，结合医学知识给出专业、准确的回答。"
    "如果涉及化验指标异常，请分析可能的原因并给出建议。"
)


def build_task_prompt(task_instruction: str = "") -> str:
    """
    构建第二层：任务指令 Prompt

    包含：当前任务的核心指令
    """
    return task_instruction if task_instruction else DEFAULT_TASK_INSTRUCTION


# ============================================================
# 第三层：上下文 Prompt（历史对话、工具结果）
# ============================================================

def messages_to_prompt(messages: List[BaseMessage]) -> str:
    """
    将消息列表拼接为上下文层文本

    格式：
        User:
        我头疼怎么办

        Assistant:
        头疼可能由多种原因引起...
    """
    parts: List[str] = []
    for msg in messages:
        if msg.role == "system":
            continue  # system 消息已在第一层处理，跳过
        elif msg.role == "user":
            parts.append(f"User:\n{msg.content}")
        elif msg.role == "assistant":
            parts.append(f"Assistant:\n{msg.content}")
        elif msg.role == "tool":
            parts.append(f"Tool [{getattr(msg, 'tool_name', '')}]:\n{msg.content}")
        else:
            parts.append(msg.content)
    return "\n\n".join(p for p in parts if p)


# ============================================================
# 第四层：格式 FewShot Prompt（输出样式、示例）
# ============================================================

DEFAULT_FORMAT_PROMPT = (
    "请用以下格式回答：\n"
    "1. 先简要说明指标含义\n"
    "2. 列出可能的异常原因\n"
    "3. 给出建议\n"
    "回答完毕后停止，不要续写对话模板。"
)


def build_format_prompt(format_prompt: str = "") -> str:
    """
    构建第四层：格式 FewShot Prompt

    包含：输出样式、参考示例、截断规则
    """
    return format_prompt if format_prompt else DEFAULT_FORMAT_PROMPT


# ============================================================
# 四层组装 -> 最终 Prompt
# ============================================================

def assemble_final_prompt(state: AgentState) -> str:
    """
    按四层架构组装最终 Prompt

    直接从 AgentState 获取所有参数：
    - 第一层（系统基底）：从 state.messages 中提取 system 消息，或用 state.user 构建
    - 第二层（任务指令）：从 state.task_queue 获取当前任务
    - 第三层（上下文）：从 state.messages 提取历史对话
    - 第四层（格式）：使用默认格式规则

    参数：
        state: AgentState 实例，包含用户画像、对话历史、任务队列等

    返回：
        完整的四层 Prompt 字符串

    组装顺序：
        [第一层：系统基底] + [第二层：任务指令] + [第三层：上下文] + [第四层：格式] + "Assistant:"
    """
    # 第一层：系统基底（从 system 消息提取，没有则用默认 + 用户画像）
    system_messages = [m for m in state.messages if m.role == "system"]
    if system_messages:
        layer1 = system_messages[0].content
    else:
        layer1 = build_system_prompt(state.user)

    # 第二层：任务指令（从任务队列取当前任务，没有则用默认）
    current_task = state.task_queue[0] if state.task_queue else ""
    layer2 = build_task_prompt(current_task)

    # RAG 层：医学知识库检索结果（如有）
    rag_text = ""
    if getattr(state, "rag_context", ""):
        rag_text = (
            "【参考医学知识库】以下是从医学知识库中检索到的相关信息，"
            "请优先参考这些内容回答用户问题：\n"
            + state.rag_context
        )

    # 第三层：上下文（历史对话，跳过 system 消息）
    layer3 = messages_to_prompt(state.messages)

    # 第四层：格式（使用默认）
    layer4 = build_format_prompt()

    # 组装
    parts = [layer1, layer2]
    if rag_text:
        parts.append(rag_text)
    if layer3:
        parts.append(layer3)
    parts.append(layer4)
    parts.append("Assistant:")

    return "\n\n".join(p for p in parts if p)
