"""
测试数据库连接 + 查看各表数据

用法：cd python_service && python scripts/test_db_connection.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.persistence.database import engine, SessionLocal, init_db
from sqlalchemy import text


def main():
    # 1. 测试连接
    print("=== 数据库连接测试 ===\n")
    print(f"数据库 URL: {engine.url}")

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print(f"✅ 连接成功！SELECT 1 = {result.scalar()}")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    # 2. 建表（如果还没有）
    init_db()

    # 3. 查看已有表
    print("\n=== 已有表 ===")
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [r[0] for r in result]
        for t in tables:
            print(f"  📋 {t}")
        if not tables:
            print("  （无表）")

    # 4. 查看各表数据量
    print("\n=== 各表数据量 ===")
    db = SessionLocal()
    try:
        from app.persistence.models import PatientProfile, SessionData
        from harness.memory.persistence.models import WorkingMemorySnapshot

        for name, model in [
            ("patient_profile", PatientProfile),
            ("session_data", SessionData),
            ("working_memory_snapshot", WorkingMemorySnapshot),
        ]:
            count = db.query(model).count()
            print(f"  {name}: {count} 条")
    finally:
        db.close()

    print("\n✅ 完成")


if __name__ == "__main__":
    main()
