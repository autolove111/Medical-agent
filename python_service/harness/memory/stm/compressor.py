"""
compressor.py
~~~~~~~~~~~~~
对话压缩器：将早期对话压缩为 200-300 字的医学摘要。

摘要内容必须包含：
- 早期主诉、关键症状
- 已做出的诊断
- 已给出的建议
- 待跟进事项
"""

import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

COMPRESS_PROMPT = """请将以下医疗对话压缩为200-300字的摘要，必须保留以下关键信息：

1. 【主诉症状】患者最初为什么来咨询
2. 【关键症状】对话中提到的所有症状和异常指标
3. 【诊断/判断】医生或助手给出的诊断或判断
4. 【建议】已给出的治疗/饮食/检查建议
5. 【待跟进】需要后续关注的事项

对话内容：
{conversation}

请用中文输出摘要，严格控制在300字以内："""


class ConversationCompressor:
    """对话压缩器"""

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None):
        self.llm_caller = llm_caller

    def compress(self, messages: List[Dict], max_chars: int = 600) -> str:
        """
        压缩对话为摘要

        参数：
            messages: 待压缩的消息列表
            max_chars: 摘要最大字符数（默认 600，约 300 字）

        返回：
            摘要文本
        """
        if not messages:
            return ""

        conversation = self._format_messages(messages)

        if self.llm_caller:
            return self._compress_with_llm(conversation, max_chars)
        return self._simple_compress(messages)

    def _compress_with_llm(self, conversation: str, max_chars: int) -> str:
        """使用 LLM 生成摘要"""
        prompt = COMPRESS_PROMPT.format(conversation=conversation)
        try:
            summary = self.llm_caller(prompt)
            # 截断到指定长度
            if len(summary) > max_chars:
                summary = summary[:max_chars] + "..."
            return summary
        except Exception as e:
            logger.error("LLM compression failed: %s", e)
            return self._simple_compress([])

    def _simple_compress(self, messages: List[Dict]) -> str:
        """
        简单压缩（降级方案，无 LLM 时使用）

        提取关键信息：用户问题数量、最后的问题、助手的建议
        """
        if not messages:
            return ""

        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

        parts = []

        # 主诉
        if user_msgs:
            first_q = user_msgs[0].get("content", "")
            if len(first_q) > 80:
                first_q = first_q[:80] + "..."
            parts.append(f"【主诉】{first_q}")

        # 统计
        parts.append(f"共{len(user_msgs)}轮对话")

        # 最后的建议
        if assistant_msgs:
            last_reply = assistant_msgs[-1].get("content", "")
            if len(last_reply) > 100:
                last_reply = last_reply[:100] + "..."
            parts.append(f"【最近建议】{last_reply}")

        return "；".join(parts)

    def _format_messages(self, messages: List[Dict]) -> str:
        """格式化消息为对话文本"""
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                parts.append(f"患者：{content}")
            elif role == "assistant":
                parts.append(f"医生：{content}")
            elif role == "system" and msg.get("type") == "summary":
                parts.append(f"[历史摘要] {content}")
        return "\n".join(parts)
