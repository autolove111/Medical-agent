"""
数据库引擎 + 会话工厂

支持 SQLite (本地开发) 和 PostgreSQL (生产部署)，
通过 .env 中的 DATABASE_URL 配置，默认为 SQLite。
"""

from __future__ import annotations
import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
DATA_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 默认 SQLite，可通过环境变量切换到 PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(DATA_DIR, 'medagent.db')}",
)

# 引擎（延迟创建，避免 psycopg2 缺失时导入失败）
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        if "postgresql" in DATABASE_URL.lower():
            _engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        else:
            _engine = create_engine(
                DATABASE_URL, echo=False,
                connect_args={"check_same_thread": False},
            )
    return _engine


Base = declarative_base()

SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_session() -> Session:
    """获取数据库会话"""
    engine = _get_engine()
    SessionLocal.configure(bind=engine)
    return SessionLocal()


def init_db():
    """创建所有表"""
    import app.persistence.models  # noqa
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized: %s", DATABASE_URL)
