"""
数据库引擎 + 会话工厂

PostgreSQL 持久化，通过 core.config 读取连接配置。
"""

from __future__ import annotations
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from core.config import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.SQLALCHEMY_DATABASE_URL

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


def get_db() -> Session:
    """获取数据库会话（FastAPI 依赖注入用）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """获取独立数据库会话（非 FastAPI 上下文）"""
    return SessionLocal()


def init_db():
    """创建所有表（首次启动时调用）"""
    import app.persistence.models  # noqa: F401 — 注册所有 ORM 模型
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at %s", DATABASE_URL)
