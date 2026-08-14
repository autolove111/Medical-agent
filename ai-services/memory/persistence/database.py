"""
数据库引擎 + 会话工厂

AI 服务独立的数据库连接。
"""

from __future__ import annotations
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 加载配置
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medlab_user:medlab_password@localhost:5432/medlab_db")

# 引擎
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类
Base = declarative_base()


def get_session() -> Session:
    """获取独立数据库会话"""
    return SessionLocal()


def init_db():
    """创建所有表（首次启动时调用）"""
    import memory.persistence.models  # noqa: F401 — 注册所有 ORM 模型
    Base.metadata.create_all(bind=engine)
    logger.info("AI Services Database initialized at %s", DATABASE_URL)
