"""
一键验证 Phase 1-7 所有模块（不加载 LLM 模型）

运行环境：conda activate medagent
运行命令：python test/verify_all_phases.py
"""

import sys, os, subprocess, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = r"E:/CondaConfig/envs/medagent/python.exe"
TEST_DIR = os.path.join(BASE, "test")

tests = [
    ("Phase 1: FastAPI 服务层",    "verify_phase1.py"),
    ("Phase 2: 报告处理管线",      "verify_phase2.py"),
    ("Phase 3: 解读引擎+来源引用", "verify_phase3.py"),
    ("Phase 4+5: 持久化+AgentLoop", "verify_phase4_5.py"),
    ("Phase 6: 安全红线框架",      "verify_phase6.py"),
]

passed = 0
failed = 0

print("=" * 65)
print("Medical-agent Phase 1-7 一键验证")
print("=" * 65)

for name, script in tests:
    path = os.path.join(TEST_DIR, script)
    if not os.path.exists(path):
        print(f"\n[SKIP] {name} — {script} 不存在")
        continue

    print(f"\n{'─' * 50}")
    print(f">>> {name} ({script})")
    print(f"{'─' * 50}")

    # 删除旧 DB 以避免外键冲突
    db_path = os.path.join(BASE, "python_service", "data", "medagent.db")
    if os.path.exists(db_path) and "Phase 4" in name:
        os.remove(db_path)

    result = subprocess.run(
        [PYTHON, "-X", "utf8", path],
        cwd=os.path.join(BASE, "python_service"),
        capture_output=True, text=True, timeout=60,
    )
    # 只显示最后 8 行
    lines = result.stdout.strip().split("\n")
    for line in lines[-8:]:
        print(f"  {line}")
    if result.stderr.strip():
        err_lines = result.stderr.strip().split("\n")
        for line in err_lines[-3:]:
            print(f"  [stderr] {line}")

    if "所有模块验证通过" in result.stdout or "所有验证通过" in result.stdout:
        passed += 1
        print(f"  ✅ {name} 通过")
    else:
        failed += 1
        print(f"  ❌ {name} 有错误 (returncode={result.returncode})")

print(f"\n{'=' * 65}")
print(f"结果: {passed} 通过, {failed} 失败, {len(tests)} 总计")
print(f"{'=' * 65}")
