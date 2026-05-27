"""验证 Phase 1 所有模块能正确导入（不触发模型加载）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'python_service'))

errors = []

def check(name):
    try:
        exec(f"import {name}")
        print(f"  [OK] {name}")
    except Exception as e:
        errors.append((name, str(e)))
        print(f"  [FAIL] {name}: {e}")

print("1. API 模型层")
check("api.models")

print("\n2. API 依赖注入")
# 这个会触发 harness 导入链，需要 transformers, torch 等
try:
    from api.dependencies import AgentPool, get_agent_pool
    pool = AgentPool()
    print(f"  [OK] AgentPool created, initial count={pool.user_count}")
except Exception as e:
    errors.append(("api.dependencies", str(e)))
    print(f"  [FAIL] api.dependencies: {e}")

print("\n3. 路由（仅导入，不启动服务）")
# 路由导入会间接触发 harness 导入
checks = ["api.routes.chat", "api.routes.report", "api.routes.user"]
for c in checks:
    try:
        mod = __import__(c, fromlist=["router"])
        print(f"  [OK] {c} (prefix={mod.router.prefix})")
    except Exception as e:
        errors.append((c, str(e)))
        print(f"  [FAIL] {c}: {e}")

print("\n4. Pydantic 模型实例化")
try:
    from api.models import ChatRequest, ChatResponse, ReportUploadResponse, IndicatorItem
    req = ChatRequest(message="肌酐120正常吗")
    print(f"  [OK] ChatRequest: {req.model_dump()}")
    resp = ChatResponse(reply="肌酐120略高于正常上限...", sources=["肾脏医学指南.txt"], turn_count=1)
    print(f"  [OK] ChatResponse")
    ind = IndicatorItem(key="creatinine", name="血肌酐", value=120.0, unit="μmol/L", ref_range="60-115 μmol/L", status="high")
    print(f"  [OK] IndicatorItem")
except Exception as e:
    errors.append(("Pydantic models", str(e)))
    print(f"  [FAIL] Pydantic models: {e}")

print("\n5. FastAPI App 创建")
try:
    from fastapi import FastAPI
    app = FastAPI(title="test")
    print(f"  [OK] FastAPI app: {app.title}")
except Exception as e:
    errors.append(("FastAPI", str(e)))
    print(f"  [FAIL] FastAPI: {e}")

print("\n" + "=" * 50)
if errors:
    print(f"验证完成，{len(errors)} 个错误:")
    for name, msg in errors:
        print(f"  - {name}: {msg}")
else:
    print("Phase 1 所有模块验证通过!")
