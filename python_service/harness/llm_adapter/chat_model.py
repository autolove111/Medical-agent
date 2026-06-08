"""
llm_adapter.chat_model
~~~~~~~~~~~~~~~~~~~~~~~
自研模型调用适配器：提供统一的 invoke（同步）和 stream（流式）接口。

核心设计：
- 零框架依赖：不依赖 LangChain/LangGraph，纯原生调用
- 接收已组装好的 prompt 字符串，只负责模型推理
- 流式输出：基于 HuggingFace TextIteratorStreamer 实现逐 token 推送
- 乱码修复：自动检测并修复模型输出的 mojibake（编码错误）
- 角色截断：模型续写出多余角色标记时自动截断，防止幻觉溢出
"""

import logging
import re
import threading
from dataclasses import dataclass
from typing import Iterable

import torch
from transformers import TextIteratorStreamer

from harness.llm_core.model_loader import ModelLoader

logger = logging.getLogger(__name__)

ROLE_MARKER_PATTERN = re.compile(
    r"(?:^|[\r\n]+|[。！？#]|回答完毕|停止)\s*(Human|User|Assistant|System)\s*[:：]",
    flags=re.IGNORECASE,
)

STOP_PATTERN = re.compile(
    r"#停止#|回答完毕[。！]?|#结束#|#不再继续#|#不再回复#|#不再回答#|#结束对话#|#结束咨询#",
)

# 话题标签泛滥检测：末尾连续 5 个以上的 #标签（含 #停止# 等重复）
HASHTAG_SPAM_PATTERN = re.compile(
    r"((?:#[^\s]+\s*){5,}[\s\S]*)$",
)


@dataclass
class Chunk:
    """流式输出的单个片段"""
    content: str


def _count_cjk(text: str) -> int:
    """统计中文字符数量"""
    return sum(1 for ch in text if "一" <= ch <= "鿿")


def _looks_like_mojibake(text: str) -> bool:
    """判断是否像乱码"""
    if not text:
        return False
    suspicious = ("Ã", "Â", "ä", "å", "æ", "ç", "è", "é", "ï", "Î", "¼")
    hits = sum(text.count(ch) for ch in suspicious)
    return hits >= 3 and _count_cjk(text) < 3


def _repair_mojibake(text: str) -> str:
    """尝试修复乱码"""
    if not _looks_like_mojibake(text):
        return text
    original_cjk = _count_cjk(text)
    for enc in ("latin1", "cp1252"):
        try:
            repaired = text.encode(enc).decode("utf-8")
        except Exception:
            continue
        if _count_cjk(repaired) > original_cjk:
            logger.info("Repaired mojibake: %s -> utf-8", enc)
            return repaired
    return text


def _truncate_at_role_marker(text: str) -> str:
    """截断模型续写出的角色标记和停止标记"""
    if not text:
        return text
    # 先检查角色标记
    match = ROLE_MARKER_PATTERN.search(text)
    if match:
        return text[: match.start()].rstrip()
    # 再检查停止标记
    match = STOP_PATTERN.search(text)
    if match:
        return text[: match.start()].rstrip()
    # 截断末尾话题标签泛滥（小模型常见幻觉）
    match = HASHTAG_SPAM_PATTERN.search(text)
    if match:
        return text[: match.start()].rstrip()
    return text


class ChatModel:
    """
    统一模型调用适配器

    只负责：prompt 字符串 -> 模型推理 -> 输出文本
    不负责：prompt 组装（由 prompt_context 模块完成）

    使用方式：
        chat = ChatModel(loader)
        prompt = assemble_final_prompt(state)  # 由调用方组装
        reply = chat.invoke(prompt)
        for chunk in chat.stream(prompt): ...
    """

    def __init__(self, loader: ModelLoader):
        self.loader = loader
        self.temperature = loader.config.temperature
        self.max_new_tokens = loader.config.max_new_tokens

    def _build_inputs(self, prompt: str):
        """prompt 字符串 -> tokenizer 编码 -> tensor（可选搬 GPU）"""
        inputs = self.loader.tokenizer(prompt, return_tensors="pt")
        if torch.cuda.is_available():
            return {k: v.to("cuda:0") for k, v in inputs.items()}
        return inputs

    def _generate_kwargs(self, inputs: dict) -> dict:
        """构建 model.generate() 的公共参数"""
        return {
            **inputs,
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.temperature > 0,
            "temperature": max(self.temperature, 1e-5),
            "pad_token_id": self.loader.tokenizer.eos_token_id,
            "eos_token_id": self.loader.tokenizer.eos_token_id,
        }

    def invoke(self, prompt: str) -> str:
        """
        同步调用：接收已组装好的 prompt，返回完整回复

        流程：
        1. prompt -> 输入 tensor
        2. model.generate() 推理
        3. 截取生成部分（去掉 prompt）
        4. 解码 -> 乱码修复 -> 角色截断
        """
        inputs = self._build_inputs(prompt)
        with torch.inference_mode():
            output = self.loader.model.generate(**self._generate_kwargs(inputs))
        generated = output[0][inputs["input_ids"].shape[1] :]
        text = self.loader.tokenizer.decode(generated, skip_special_tokens=True).strip()
        text = _repair_mojibake(text)
        text = _truncate_at_role_marker(text)
        return text

    def stream(self, prompt: str) -> Iterable[Chunk]:
        """
        流式调用：逐 token 生成，适合前端实时展示
        """
        inputs = self._build_inputs(prompt)

        streamer = TextIteratorStreamer(
            self.loader.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        kwargs = self._generate_kwargs(inputs)
        kwargs["streamer"] = streamer
        worker = threading.Thread(
            target=self.loader.model.generate, kwargs=kwargs, daemon=True
        )
        worker.start()

        pending = ""
        tail_guard = 48  # 增大缓冲区以容纳完整的停止标记
        for text in streamer:
            if text:
                pending += _repair_mojibake(text)

                # 检查角色标记（幻觉续写）
                match = ROLE_MARKER_PATTERN.search(pending)
                if not match:
                    # 检查停止标记
                    match = STOP_PATTERN.search(pending)
                if not match:
                    # 检查话题标签泛滥（5+ 个连续 #标签）
                    match = HASHTAG_SPAM_PATTERN.search(pending)
                if match:
                    safe = pending[: match.start()]
                    if safe:
                        yield Chunk(content=safe)
                    return

                if len(pending) > tail_guard:
                    safe = pending[:-tail_guard]
                    if safe:
                        yield Chunk(content=safe)
                    pending = pending[-tail_guard:]

        if pending:
            pending = _truncate_at_role_marker(pending)
            if pending:
                yield Chunk(content=pending)
