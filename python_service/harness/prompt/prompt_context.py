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
- token 预算管理：确保 prompt 不超过分配的 token 限制
"""

import logging
from typing import List, Optional

from harness.state.agent_state import UserProfile, BaseMessage, AgentState

logger = logging.getLogger(__name__)

# tokenizer 实例（延迟初始化）
_tokenizer = None


def _get_tokenizer():
    """获取 tokenizer 实例（延迟加载）"""
    global _tokenizer
    if _tokenizer is None:
        try:
            from harness.llm_core.model_loader import ModelLoader
            loader = ModelLoader()
            _tokenizer = loader.tokenizer
        except Exception:
            _tokenizer = None
    return _tokenizer


def count_tokens(text: str) -> int:
    """
    统计文本的 token 数量

    优先使用模型的 tokenizer，如果不可用则使用简单的字符数估算
    """
    tokenizer = _get_tokenizer()
    if tokenizer:
        try:
            tokens = tokenizer.encode(text, add_special_tokens=False)
            return len(tokens)
        except Exception:
            pass

    # 回退方案：简单估算（中文约 1.5 token/字，英文约 0.25 token/词）
    cjk_count = sum(1 for ch in text if "一" <= ch <= "鿿")
    other_count = len(text) - cjk_count
    return int(cjk_count * 1.5 + other_count * 0.25)


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """
    将文本截断到指定的 token 数量

    使用二分法找到合适的截断点
    """
    if count_tokens(text) <= max_tokens:
        return text

    # 二分法查找合适的截断点
    left, right = 0, len(text)
    best = left

    while left <= right:
        mid = (left + right) // 2
        truncated = text[:mid]
        tokens = count_tokens(truncated)

        if tokens <= max_tokens:
            best = mid
            left = mid + 1
        else:
            right = mid - 1

    return text[:best]


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
    "请根据用户问题的类型灵活回答：\n"
    "- 如果是关于化验指标的问题，请说明指标含义、异常原因、给出建议\n"
    "- 如果是简单的问答（如询问症状、历史记录等），请直接回答\n"
    "- 回答完毕后停止，不要续写对话模板"
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

def assemble_final_prompt(state: AgentState, prompt_max_tokens: Optional[int] = None) -> str:
    """
    按四层架构组装最终 Prompt

    直接从 AgentState 获取所有参数：
    - 第一层（系统基底）：从 state.system_prompt 获取，或用 state.user 构建
    - 第二层（任务指令）：从 state.task_queue 获取当前任务
    - RAG层：从 state.rag_context 获取医学知识库检索结果（限制长度）
    - 历史对话层：从 state.stm 获取完整对话历史（最近5轮）
    - 第四层（格式）：使用默认格式规则

    参数：
        state: AgentState 实例，包含用户画像、对话历史、任务队列等
        prompt_max_tokens: 提示词最大 token 数量（可选，用于控制上下文窗口分配）

    返回：
        完整的四层 Prompt 字符串

    组装顺序：
        [第一层：系统基底] + [第二层：任务指令] + [RAG层] + [历史对话层] + [第四层：格式] + "Assistant:"
    """
    # 第一层：系统基底（从 system_prompt 字段获取，没有则用默认 + 用户画像）
    if state.system_prompt:
        layer1 = state.system_prompt
    else:
        layer1 = build_system_prompt(state.user)

    # 第二层：任务指令（从任务队列取当前任务，没有则用默认）
    current_task = state.task_queue[0] if state.task_queue else ""
    layer2 = build_task_prompt(current_task)

    # RAG 层：医学知识库检索结果（如有，限制长度避免占用太多 token）
    rag_text = ""
    if getattr(state, "rag_context", ""):
        rag_context = state.rag_context
        # 限制 RAG 内容长度，避免 prompt 过长
        max_rag_length = 1500
        if len(rag_context) > max_rag_length:
            rag_context = rag_context[:max_rag_length] + "\n...(内容已截断)"
        rag_text = (
            "【参考医学知识库】以下是从医学知识库中检索到的相关信息，"
            "请优先参考这些内容回答用户问题：\n"
            + rag_context
        )

    # 短期记忆层：完整历史对话（只保留最近N轮，避免prompt过长）
    short_memory_text = ""
    if getattr(state, "stm", None):
        # 获取最近的对话消息（最多保留最近5轮 = 10条消息）
        recent_msgs = state.stm.get_recent_messages(n=5)
        # 过滤掉 summary 类型，只保留 user/assistant 对话
        conversation_msgs = [
            m for m in recent_msgs
            if m.get("role") in ("user", "assistant")
        ]
        if conversation_msgs:
            parts = []
            for msg in conversation_msgs:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    parts.append(f"User:\n{content}")
                elif role == "assistant":
                    parts.append(f"Assistant:\n{content}")
            short_memory_text = "\n\n".join(parts)

    # 第四层：格式（使用默认）
    layer4 = build_format_prompt()

    # 组装（不再包含 Layer 3 完整历史，避免重复）
    parts = [layer1, layer2]
    if rag_text:
        parts.append(rag_text)
    if short_memory_text:
        parts.append(short_memory_text)
    parts.append(layer4)
    parts.append("Assistant:")

    prompt = "\n\n".join(p for p in parts if p)

    # 如果指定了 token 限制，进行截断
    if prompt_max_tokens is not None:
        current_tokens = count_tokens(prompt)
        if current_tokens > prompt_max_tokens:
            # 优先截断历史对话（最后添加的部分）
            logger.warning(
                "Prompt exceeds token limit: %d > %d, truncating...",
                current_tokens, prompt_max_tokens
            )

            # 计算各部分的 token 数
            layer1_tokens = count_tokens(layer1)
            layer2_tokens = count_tokens(layer2)
            rag_tokens = count_tokens(rag_text) if rag_text else 0
            memory_tokens = count_tokens(short_memory_text) if short_memory_text else 0
            layer4_tokens = count_tokens(layer4)
            suffix_tokens = count_tokens("Assistant:")

            # 计算可用于历史对话的 token 数
            fixed_tokens = layer1_tokens + layer2_tokens + rag_tokens + layer4_tokens + suffix_tokens
            available_for_memory = prompt_max_tokens - fixed_tokens

            if available_for_memory > 0 and short_memory_text:
                # 截断历史对话
                short_memory_text = truncate_to_token_limit(short_memory_text, available_for_memory)
                # 重新组装
                parts = [layer1, layer2]
                if rag_text:
                    parts.append(rag_text)
                if short_memory_text:
                    parts.append(short_memory_text)
                parts.append(layer4)
                parts.append("Assistant:")
                prompt = "\n\n".join(p for p in parts if p)
            else:
                # 如果固定部分已经超过限制，截断整个 prompt
                prompt = truncate_to_token_limit(prompt, prompt_max_tokens)
                logger.warning("Fixed parts exceed limit, truncated entire prompt")

    return prompt
