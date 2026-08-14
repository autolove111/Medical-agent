"""
question_gen.question_generator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Plan 综合完成后，用 LLM 生成用户推荐问题
"""
import json
import logging

from prompts import load_prompt
from llm.chat_model import ChatModel

logger = logging.getLogger(__name__)

# 最大历史长度（字符数），超出则截断
MAX_HISTORY_CHARS = 3000


def generate_report_questions(messages: list[dict]) -> list[str]:
    """
    根据对话历史生成推荐问题

    Args:
        messages: 对话历史消息列表（含系统提示、用户消息、助手分析等）

    Returns:
        问题列表，最多4个
    """
    # 格式化对话历史为文本（过滤掉工具调用相关消息）
    formatted = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            formatted.append(f"用户：{content}")
        elif role == "assistant" and content:
            # 跳过 content 为 null 的 assistant 消息（工具调用）
            formatted.append(f"助手：{content}")

    if not formatted:
        return []

    history_text = "\n".join(formatted)

    # 截断过长的历史
    if len(history_text) > MAX_HISTORY_CHARS:
        history_text = history_text[-MAX_HISTORY_CHARS:]

    # 加载 prompt 模板
    system_messages = load_prompt("report/questions", messages=history_text)

    # 加一条 user 消息触发 LLM 生成
    prompt_messages = system_messages + [
        {"role": "user", "content": "请根据以上对话历史，生成 4 个用户最可能追问的问题。"}
    ]

    try:
        chat_model = ChatModel()
        response = chat_model.invoke(prompt_messages)
        raw = response.choices[0].message.content.strip()

        # 兼容 LLM 返回 ```json ... ``` 的情况
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        questions = json.loads(raw)
        if isinstance(questions, list):
            return [str(q).strip() for q in questions if q][:4]
    except Exception as e:
        logger.warning("generate_report_questions failed: %s", e)

    return []
