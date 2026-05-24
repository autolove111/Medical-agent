"""
llm_core.model_loader
~~~~~~~~~~~~~~~~~~~~~
自研模型加载器：负责从本地路径加载 HuggingFace 模型和 tokenizer。

核心设计：
- 单例模式：全局只加载一次模型，避免重复占用显存
- 线程安全：双重检查锁（DCL），多线程并发时不会重复初始化
- 懒加载：首次访问 tokenizer/model 时才触发加载，启动更快
- 量化支持：自动检测 CUDA + bitsandbytes，降级到 CPU fp32
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置参数，统一管理所有加载相关的超参"""

    model_path: str                       # 本地模型目录路径
    use_4bit: bool = True                 # 是否启用 4-bit 量化（省显存）
    quant_type: str = "nf4"               # 量化类型，nf4 是 QLoRA 推荐方案
    use_double_quant: bool = True         # 二次量化，进一步压缩显存占用
    temperature: float = 0.7              # 生成温度，越高越随机
    max_new_tokens: int = 2000            # 单次最大生成 token 数


class ModelLoader:
    """
    模型加载器（单例）

    使用方式：
        config = ModelConfig(model_path="../models/Qwen2.5-7B-Instruct")
        loader = ModelLoader.init(config)   # 首次初始化
        loader = ModelLoader()              # 后续获取同一实例

        tokenizer = loader.tokenizer        # 自动触发懒加载
        model = loader.model
    """

    # ---- 单例状态（类级别共享） ----
    _instance: Optional["ModelLoader"] = None
    _lock = threading.Lock()       # 保证并发安全
    _tokenizer = None              # 分词器实例
    _model = None                  # 模型实例

    def __new__(cls, config: Optional[ModelConfig] = None):
        """双重检查锁（DCL）单例：第一次创建时写入 config"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj.config = config
                    cls._instance = obj
        return cls._instance

    @classmethod
    def init(cls, config: ModelConfig) -> "ModelLoader":
        """显式初始化：重置单例并传入新配置（用于启动时调用一次）"""
        cls._instance = None
        return cls(config)

    def _resolve_quantization_config(self) -> Optional[BitsAndBytesConfig]:
        """
        解析量化配置：按优先级判断是否启用 4-bit 量化
        降级链：4-bit 配置 -> CUDA 不可用 -> bitsandbytes 未装 -> 回退 fp32
        """
        if not self.config.use_4bit:
            logger.info("4-bit quantization disabled by config")
            return None

        if not torch.cuda.is_available():
            logger.warning("CUDA unavailable, falling back to fp32")
            return None

        try:
            import bitsandbytes  # noqa: F401
        except ImportError:
            logger.warning("bitsandbytes not installed, falling back to fp32")
            return None

        logger.info(
            "Enabling 4-bit quantization | type=%s double_quant=%s",
            self.config.quant_type,
            self.config.use_double_quant,
        )
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=self.config.quant_type,
            bnb_4bit_use_double_quant=self.config.use_double_quant,
            bnb_4bit_compute_dtype=torch.float16,
        )

    def load(self):
        """
        实际加载模型和 tokenizer（懒加载入口）

        流程：
        1. 快速检查是否已加载（无锁，避免不必要的等待）
        2. 加锁后二次检查（防止并发重复加载）
        3. 解析量化配置
        4. 加载 tokenizer（分词器）
        5. 加载 model（语言模型本体）
        6. 切 eval 模式（关闭 dropout 等训练行为）
        """
        # 第一次检查：已加载则直接返回（无锁快速路径）
        if self._model is not None and self._tokenizer is not None:
            return

        with self._lock:
            # 第二次检查：防止等待锁期间其他线程已完成加载
            if self._model is not None and self._tokenizer is not None:
                return

            path = self.config.model_path
            logger.info("Loading model from %s", path)

            # Step 1: 解析量化配置
            quant_config = self._resolve_quantization_config()

            # Step 2: 加载 tokenizer（负责文本 <-> token ID 的转换）
            tokenizer = AutoTokenizer.from_pretrained(
                path,
                trust_remote_code=True,   # Qwen 等模型需要加载自定义代码
                local_files_only=True,     # 纯本地加载，不联网
            )

            # Step 3: 构建模型加载参数
            model_kwargs = {
                "trust_remote_code": True,
                "local_files_only": True,
            }
            if quant_config is not None:
                # 有量化：用 bitsandbytes 4-bit 加载，显存占用约 4-5 GB（7B 模型）
                model_kwargs["quantization_config"] = quant_config
                model_kwargs["device_map"] = {"": 0}  # 全部放到 GPU 0
            else:
                # 无量化：fp16（GPU）或 fp32（CPU）
                model_kwargs["torch_dtype"] = (
                    torch.float16 if torch.cuda.is_available() else torch.float32
                )
                model_kwargs["device_map"] = (
                    "auto" if torch.cuda.is_available() else None
                )

            # Step 4: 加载模型本体
            model = AutoModelForCausalLM.from_pretrained(path, **model_kwargs)

            # CPU 回退：如果没量化也没 GPU，手动搬到 CPU
            if quant_config is None and not torch.cuda.is_available():
                model = model.to("cpu")

            # Step 5: 切换到推理模式（关闭 dropout、batch norm 等训练行为）
            model.eval()

            # Step 6: 写入类变量，后续所有实例共享
            self._tokenizer = tokenizer
            self._model = model
            logger.info("Model loaded successfully")

    @property
    def tokenizer(self):
        """tokenizer 属性访问，首次访问时自动触发 load()"""
        self.load()
        return self._tokenizer

    @property
    def model(self):
        """model 属性访问，首次访问时自动触发 load()"""
        self.load()
        return self._model
