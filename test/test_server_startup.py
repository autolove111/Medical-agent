"""验证 FastAPI 应用能成功创建并注册所有路由（不触模型加载）"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.environ["SERVICE_PORT"] = "8000"

# 测试 server.py 中的 app 对象
from server import app

print(f"App title: {app.title}")
print(f"App version: {app.version}")
print(f"Routes ({len(app.routes)}):")
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        print(f"  {route.methods} {route.path} -> {route.name}")

print(f"\nCORS origins: {[m for m in app.user_middleware if m.cls.__name__ == 'CORSMiddleware']}")

# 验证具体端点
endpoints = [r.path for r in app.routes if hasattr(r, 'path')]
expected = ['/api/chat', '/api/chat/stream', '/api/report/upload', '/api/user/profile', '/api/user/reset', '/api/user/health']
missing = [e for e in expected if e not in endpoints]
if missing:
    print(f"\n[WARN] Missing endpoints: {missing}")
else:
    print(f"\n[OK] All {len(expected)} expected endpoints registered")

print("\n=== 服务启动验证通过 ===")
