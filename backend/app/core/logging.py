"""
日志配置模块
统一管理项目的日志输出
"""
import logging
import logging.handlers
import sys
from pathlib import Path

# 日志目录
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO"):
    """
    配置日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # 根日志器
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有的处理器（避免重复）
    root.handlers.clear()

    # 1. 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    )
    root.addHandler(console_handler)

    # 2. 应用日志文件（按大小轮转）
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    )
    root.addHandler(file_handler)

    # 3. 错误日志文件（只记录 ERROR 及以上）
    error_handler = logging.FileHandler(
        LOG_DIR / "error.log",
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    )
    root.addHandler(error_handler)

    # 降低第三方库日志噪音
    _silence_noisy_loggers()

    logging.getLogger(__name__).info(
        "日志系统初始化完成，级别: %s，目录: %s", level, LOG_DIR
    )


def _silence_noisy_loggers():
    """降低第三方库的日志级别"""
    noisy_loggers = [
        "transformers",
        "sentence_transformers",
        "uvicorn.access",
        "httpx",
        "httpcore",
        "asyncio",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志器

    Args:
        name: 日志器名称，通常使用 __name__

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)
