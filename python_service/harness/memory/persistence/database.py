"""
数据库引擎 + 会话工厂

复用 app.persistence.database 的引擎，避免重复创建连接池。
"""

from __future__ import annotations
from sqlalchemy.orm import Session

from app.persistence.database import engine, SessionLocal, Base, init_db


def get_session() -> Session:
    """获取独立数据库会话"""
    return SessionLocal()
