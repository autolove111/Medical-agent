import logging
import re
import threading
from dataclasses import dataclass
from typing import Iterable, List, Optional

import torch
from langchain_core.messages import AIMessage
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TextIteratorStreamer,
)

from core.config import settings

logger = logging.getLogger(__name__)

ROLE_MARKER_PATTERN = re.compile(
    r"(?:^|[\r\n]+)\s*(Human|User|Assistant|System)\s*[:：]",
    flags=re.IGNORECASE,
)


@dataclass
class _Chunk:
    content: str


def _count_cjk(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    suspicious = ("Ã", "Â", "ä", "å", "æ", "ç", "è", "é", "ï", "Î", "¼")
    suspicious_hits = sum(text.count(ch) for ch in suspicious)
    return suspicious_hits >= 3 and _count_cjk(text) < 3


def _repair_mojibake(text: str) -> str:
    if not _looks_like_mojibake(text):
        return text

    original_cjk = _count_cjk(text)
    for source_encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(source_encoding).decode("utf-8")
        except Exception:
            continue
        if _count_cjk(repaired) > original_cjk:
            logger.info("Repaired mojibake text using %s -> utf-8", source_encoding)
            return repaired
    return text


def _messages_to_prompt(messages: List) -> str:
    parts: List[str] = []
    for message in messages:
        msg_type = getattr(message, "type", "")
        content = getattr(message, "content", "")
        if msg_type == "system":
            parts.append(f"System:\n{content}")
        elif msg_type == "human":
            parts.append(f"User:\n{content}")
        else:
            parts.append(str(content))
    parts.append("Assistant:")
    return "\n\n".join(part for part in parts if part)


def _truncate_at_role_marker(text: str) -> str:
    if not text:
        return text

    match = ROLE_MARKER_PATTERN.search(text)
    if not match:
        return text
    return text[: match.start()].rstrip()


class LocalTransformersChatModel:
    _tokenizer = None
    _model = None
    _lock = threading.Lock()

    def __init__(self):
        self.temperature = settings.TEMPERATURE
        self.max_new_tokens = settings.MAX_TOKENS
        self.model_path = settings.LLM_MODEL_PATH
        self._ensure_loaded()

    @staticmethod
    def _resolve_quantization_config() -> Optional[BitsAndBytesConfig]:
        if not settings.LLM_USE_4BIT:
            logger.info("4-bit quantization disabled by config")
            return None

        if not torch.cuda.is_available():
            logger.warning("4-bit quantization requested but CUDA is unavailable; falling back")
            return None

        try:
            import bitsandbytes  # noqa: F401
        except ImportError:
            logger.warning(
                "4-bit quantization requested but bitsandbytes is not installed; falling back"
            )
            return None

        compute_dtype = torch.float16
        logger.info(
            "Enabling 4-bit quantization | quant_type=%s double_quant=%s dtype=%s",
            settings.LLM_4BIT_QUANT_TYPE,
            settings.LLM_4BIT_USE_DOUBLE_QUANT,
            compute_dtype,
        )
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=settings.LLM_4BIT_QUANT_TYPE,
            bnb_4bit_use_double_quant=settings.LLM_4BIT_USE_DOUBLE_QUANT,
            bnb_4bit_compute_dtype=compute_dtype,
        )

    @classmethod
    def _ensure_loaded(cls):
        if cls._model is not None and cls._tokenizer is not None:
            return

        with cls._lock:
            if cls._model is not None and cls._tokenizer is not None:
                return

            logger.info("Loading local transformers model from %s", settings.LLM_MODEL_PATH)
            quantization_config = cls._resolve_quantization_config()
            tokenizer = AutoTokenizer.from_pretrained(
                settings.LLM_MODEL_PATH,
                trust_remote_code=True,
                local_files_only=True,
            )
            model_kwargs = {
                "trust_remote_code": True,
                "local_files_only": True,
            }
            if quantization_config is not None:
                model_kwargs["quantization_config"] = quantization_config
                model_kwargs["device_map"] = {"": 0}
            else:
                model_kwargs["torch_dtype"] = (
                    torch.float16 if torch.cuda.is_available() else torch.float32
                )
                model_kwargs["device_map"] = "auto" if torch.cuda.is_available() else None

            model = AutoModelForCausalLM.from_pretrained(
                settings.LLM_MODEL_PATH,
                **model_kwargs,
            )
            if quantization_config is None and not torch.cuda.is_available():
                model = model.to("cpu")
            model.eval()

            cls._tokenizer = tokenizer
            cls._model = model

    @property
    def tokenizer(self):
        return self.__class__._tokenizer

    @property
    def model(self):
        return self.__class__._model

    def _build_inputs(self, messages: List):
        prompt = _messages_to_prompt(messages)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        if torch.cuda.is_available():
            return {key: value.to("cuda:0") for key, value in inputs.items()}
        return inputs

    def invoke(self, messages: List) -> AIMessage:
        inputs = self._build_inputs(messages)
        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0,
                temperature=max(self.temperature, 1e-5),
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        text = _repair_mojibake(text)
        text = _truncate_at_role_marker(text)
        return AIMessage(content=text)

    def stream(self, messages: List) -> Iterable[_Chunk]:
        inputs = self._build_inputs(messages)
        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        kwargs = {
            **inputs,
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.temperature > 0,
            "temperature": max(self.temperature, 1e-5),
            "pad_token_id": self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "streamer": streamer,
        }
        worker = threading.Thread(target=self.model.generate, kwargs=kwargs, daemon=True)
        worker.start()

        pending = ""
        tail_guard = 32
        for text in streamer:
            if text:
                pending += _repair_mojibake(text)

                match = ROLE_MARKER_PATTERN.search(pending)
                if match:
                    safe_text = pending[: match.start()]
                    if safe_text:
                        yield _Chunk(content=safe_text)
                    return

                if len(pending) > tail_guard:
                    safe_text = pending[:-tail_guard]
                    if safe_text:
                        yield _Chunk(content=safe_text)
                    pending = pending[-tail_guard:]

        if pending:
            yield _Chunk(content=pending)
