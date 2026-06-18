"""
短期记忆存储 — Function Calling 消息格式

存储 OpenAI 标准消息格式：
  {"role": "user",      "content": "..."}
  {"role": "assistant", "content": "..."}
  {"role": "assistant", "tool_calls": [...]}
  {"role": "tool",      "tool_call_id": "...", "content": "..."}
"""



from __future__ import annotations
from dataclasses import dataclass, field
from harness.context_window.window_control import ContextWindowControl




class ShortMemoryStore:
    def __init__(self):
        self.messages: list[dict] = []
        self.summary: list[dict] = []
        self.message_len: int = 0
        
        # 缓存 window_control 实例
        from harness.context_window.window_control import ContextWindowControl
        self.window_control = ContextWindowControl()

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})
        self.message_len += len(content)
        
        # 检查是否需要压缩
        if self.message_len > self.window_control.get_limit("history").chars:
            self.compress_messages(
                summary_len=self.window_control.get_limit("summary").chars
            )

    def add_assistant_message(self, content: str) -> None:
        """添加助手文本回复"""
        self.messages.append({"role": "assistant", "content": content})
        self.message_len += len(content)

    def add_assistant_tool_calls(self, content: str, tool_calls: list[dict]) -> None:
        """添加助手的工具调用请求"""
        # 计算长度
        total_len = len(content)
        for tc in tool_calls:
            fn = tc.get("function", {})
            total_len += len(fn.get("name", ""))
            total_len += len(fn.get("arguments", ""))
        
        self.message_len += total_len
        
        msg = {"role": "assistant", "tool_calls": tool_calls}
        if content:
            msg["content"] = content
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """添加工具执行结果"""
        self.message_len += len(content) + len(tool_call_id)
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    

    def compress_messages(self, summary_len: int) -> None:
        from harness.llm_adapter.chat_model import ChatModel
        llm = ChatModel()
        
        if len(self.messages) < 4:
            return

        # 取最早的一半消息
        mid = len(self.messages) // 2
        old_messages = self.messages[:mid]

        # 构建待压缩的内容
        content_parts = []
        
        if self.summary:
            content_parts.append(f"【已有摘要】\n{self.summary[0]['content']}")
        
        conversation = "\n".join([
            f"[{m.get('role', '?')}] {m.get('content', '')}" 
            for m in old_messages
        ])
        content_parts.append(f"【待压缩对话】\n{conversation}")
        
        combined_content = "\n\n".join(content_parts)
        
        system_content = (
            f"请将以下医疗问诊对话段落压缩为要点摘要，遵循规则：\n"
            "1. 保留：症状、用药、过敏史、诊断结论、数字参数、用户明确偏好\n"
            "2. 删除：礼貌用语、重复确认、过程描述、非结论性思考\n"
            "3. 合并：将分散的相关信息合并为一条\n"
            "4. 保持时序：按原顺序提炼\n"
            f"5. 字数不能超过{summary_len}个字符 \n"
            "\n"
            "输出格式（纯文本，每行一个要点）：\n"
            "- [要点1]\n"
            "- [要点2]"
        )
        
        compress_prompt = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": combined_content}
        ]
        
        response = llm.invoke(compress_prompt)
        summary_text = response.choices[0].message.content
        
        # 更新 summary
        self.summary = [{"role": "system", "content": f"会话摘要（基于历史消息压缩生成）:\n{summary_text}"}]
        
        # 更新 messages（删除已压缩的部分）
        self.messages = self.messages[mid:]
        
        # 重新计算 message_len
        self.message_len = sum(len(m.get("content", "")) for m in self.messages)
