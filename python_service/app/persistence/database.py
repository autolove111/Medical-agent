"""
SQLite 数据库引擎 + 会话工厂

轻量级本地持久化，零配置，适合开发和生产初期。
后续可平滑迁移到 PostgreSQL（只需改 DATABASE_URL）。
"""

from __future__ import annotations
import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base

logger = logging.getLogger(__name__)

# 数据库文件放在 python_service/data/ 下
_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
DATA_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'medagent.db')}"

# 引擎（echo=False 生产环境）
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 允许多线程
    pool_pre_ping=True,
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类
Base = declarative_base()


# SQLite 外键支持
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
    # 确保所有模型已导入到 Base.metadata
    import app.persistence.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at %s", DATABASE_URL)
