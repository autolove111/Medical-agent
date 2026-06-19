"""
llm_adapter.chat_model
~~~~~~~~~~~~~~~~~~~~~~~
模型调用适配器。

invoke(messages, tools) → ChatResponse
  1. tokenizer.apply_chat_template(messages, tools=tools)
  2. model.generate()
  3. 解析输出 → ChatResponse
"""

import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Iterable

import torch
from transformers import TextIteratorStreamer

from harness.llm_core.model_loader import ModelLoader

logger = logging.getLogger(__name__)


# ============================================================
# OpenAI 标准格式
# ============================================================

@dataclass
class Function:
    name: str
    arguments: str


@dataclass
class ToolCall:
    id: str
    type: str = "function"
    function: Function = field(default_factory=lambda: Function(name="", arguments="{}"))

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


@dataclass
class Message:
    role: str = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Choice:
    message: Message = field(default_factory=Message)
    finish_reason: str = "stop"


@dataclass
class ChatResponse:
    choices: list[Choice] = field(default_factory=list)


@dataclass
class Chunk:
    content: str



# ============================================================
# ChatModel
# ============================================================

# ============================================================
# 本地模型版本（暂时注释）
# ============================================================
#
# class ChatModel:
#     def __init__(self):
#         self.loader = ModelLoader()
#         self.temperature = self.loader.config.temperature
#         self.max_new_tokens = self.loader.config.max_new_tokens
#
#     def invoke(self, messages, tools=None):
#         tokenizer = self.loader.tokenizer
#         if tools:
#             prompt = tokenizer.apply_chat_template(messages, tools=tools, add_generation_prompt=True, tokenize=False)
#         else:
#             prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
#         inputs = tokenizer(prompt, return_tensors="pt")
#         if torch.cuda.is_available():
#             inputs = {k: v.to("cuda:0") for k, v in inputs.items()}
#         gen_kwargs = {**inputs, "max_new_tokens": self.max_new_tokens, "do_sample": self.temperature > 0,
#                       "temperature": max(self.temperature, 1e-5), "pad_token_id": tokenizer.eos_token_id,
#                       "eos_token_id": tokenizer.eos_token_id}
#         with torch.inference_mode():
#             output = self.loader.model.generate(**gen_kwargs)
#         generated = output[0][inputs["input_ids"].shape[1]:]
#         text = tokenizer.decode(generated, skip_special_tokens=True).strip()
#         tool_calls = _parse_tool_calls(text)
#         if tool_calls:
#             return ChatResponse(choices=[Choice(message=Message(role="assistant", content=text, tool_calls=tool_calls), finish_reason="tool_calls")])
#         return ChatResponse(choices=[Choice(message=Message(role="assistant", content=text), finish_reason="stop")])
#
#     def stream(self, messages):
#         tokenizer = self.loader.tokenizer
#         prompt = tokenizer.apply_chat_template(messages=messages, add_generation_prompt=True, tokenize=False)
#         inputs = tokenizer(prompt, return_tensors="pt")
#         if torch.cuda.is_available():
#             inputs = {k: v.to("cuda:0") for k, v in inputs.items()}
#         streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
#         gen_kwargs = {**inputs, "max_new_tokens": self.max_new_tokens, "do_sample": self.temperature > 0,
#                       "temperature": max(self.temperature, 1e-5), "pad_token_id": tokenizer.eos_token_id,
#                       "eos_token_id": tokenizer.eos_token_id, "streamer": streamer}
#         worker = threading.Thread(target=self.loader.model.generate, kwargs=gen_kwargs, daemon=True)
#         worker.start()
#         for text in streamer:
#             if text:
#                 yield Chunk(content=text)


# ============================================================
# API 版本（当前使用）
# ============================================================

class ChatModel:
    """模型调用适配器 — API 版本"""

    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            api_key="tp-cvyhrlmkjyiy9sp1ic7up8qtgoyyjy01qns18wrt0vm3rvnq",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
        )
        self.model = "mimo-v2.5"

    @staticmethod
    def _flatten_messages(messages: list) -> list[dict]:
        """将嵌套的消息列表扁平化为 dict 列表"""
        flat = []
        for item in messages:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return flat

    def invoke(self, messages: list[dict], tools: list[dict] = None):
        messages = self._flatten_messages(messages)
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        # Mimo API 不支持 role: "tool"，转成 "user"
        for msg in kwargs["messages"]:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                msg["role"] = "user"

        return self.client.chat.completions.create(**kwargs)

    def stream(self, messages: list[dict]):
        return self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True,
        )
