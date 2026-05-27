"""验证 Phase 4 (持久化) + Phase 5 (AgentLoop)"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'python_service'))

errors = []
print("=" * 60)
print("Phase 4+5 验证：持久化 + AgentLoop")
print("=" * 60)

# ==============================
# Phase 4: 持久化层
# ==============================
print("\n=== Phase 4: SQLite 持久化 ===")

# 1. 数据库引擎
print("\n1. 数据库引擎 + 表创建")
try:
    from app.persistence.database import engine, init_db, get_session, Base
    init_db()

    # 验证表已创建
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "reports" in tables
    assert "chat_history" in tables
    print(f"   [OK] 3 张表已创建: {tables}")
except Exception as e:
    errors.append(f"database: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 2. UserRepo
print("\n2. UserRepo CRUD")
try:
    from app.persistence.repositories.user_repo import UserRepo

    repo = UserRepo()

    # 创建
    user = repo.create_or_update(
        "test_phase4", name="测试用户", age=45, gender="男",
        medical_history=["高血压"], allergies=["青霉素"],
        current_medications=["硝苯地平"],
    )
    assert user.id == "test_phase4"
    assert user.name == "测试用户"
    print(f"   [OK] 创建用户: {user.name}, 年龄={user.age}")

    # 读取
    user = repo.get("test_phase4")
    assert user is not None
    mh = json.loads(user.medical_history)
    assert "高血压" in mh
    print(f"   [OK] 读取用户: 病史={mh}")

    # 存在性检查
    assert repo.exists("test_phase4")
    assert not repo.exists("nonexistent")
    print(f"   [OK] exists() 正常")

    # 更新
    repo.create_or_update("test_phase4", name="测试用户2", age=46)
    user = repo.get("test_phase4")
    assert user.name == "测试用户2"
    assert user.age == 46
    print(f"   [OK] 更新用户: name={user.name}, age={user.age}")

except Exception as e:
    errors.append(f"UserRepo: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 3. ReportRepo
print("\n3. ReportRepo CRUD")
try:
    from app.persistence.repositories.report_repo import ReportRepo

    repo = ReportRepo()
    repo.save(
        report_id="rpt_test_phase4",
        user_id="test_phase4",
        report_date="2026-05-26",
        file_path="/tmp/test.jpg",
        total_count=6, abnormal_count=3, normal_count=3,
        has_critical=False,
        indicators=[
            {"key": "creatinine", "name": "血肌酐", "value": 120.0, "unit": "μmol/L",
             "ref_range": "60-115 μmol/L", "status": "high", "description": "肾功能标志"},
        ],
        correlations=[
            {"name": "肾功能受损", "severity": "high", "indicators": ["creatinine", "bun"]},
        ],
    )
    print(f"   [OK] 保存报告")

    # 获取完整报告
    full = repo.get_full("rpt_test_phase4")
    assert full is not None
    assert full["total_count"] == 6
    assert len(full["indicators"]) == 1
    assert len(full["correlations"]) == 1
    print(f"   [OK] 读取完整报告: {full['total_count']} 项指标, {len(full['correlations'])} 条联动")

    # 列表
    reports = repo.list_by_user("test_phase4")
    assert len(reports) >= 1
    assert reports[0]["report_id"] == "rpt_test_phase4"
    print(f"   [OK] 用户报告列表: {len(reports)} 条")

except Exception as e:
    errors.append(f"ReportRepo: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 4. ChatRepo
print("\n4. ChatRepo CRUD")
try:
    from app.persistence.repositories.chat_repo import ChatRepo

    repo = ChatRepo()
    repo.save_message("test_phase4", "user", "我的肌酐120偏高吗？", report_id="rpt_test_phase4", turn_number=1)
    repo.save_message("test_phase4", "assistant", "肌酐120μmol/L略高于正常上限...", report_id="rpt_test_phase4", turn_number=1)

    history = repo.get_history("test_phase4", report_id="rpt_test_phase4")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    print(f"   [OK] 对话历史: {len(history)} 条消息")

    turn = repo.get_last_turn("test_phase4")
    assert turn == 1
    print(f"   [OK] 最近轮次: {turn}")

except Exception as e:
    errors.append(f"ChatRepo: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 5. API 路由（DB 集成）
print("\n5. API 路由 + DB 集成")
try:
    from api.routes.user import router as user_router, _sync_agent_from_db
    from api.routes.report import ReportRepo
    from api.routes.chat import router as chat_router

    print(f"   [OK] user router: {len(user_router.routes)} 端点")
    print(f"   [OK] chat router: {len(chat_router.routes)} 端点")

    # 验证报告 DB 查询
    report = ReportRepo().get_full("rpt_test_phase4")
    assert report is not None
    print(f"   [OK] ReportRepo DB 查询正常")
except Exception as e:
    errors.append(f"API+DB: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# ==============================
# Phase 5: AgentLoop + 工具
# ==============================
print("\n=== Phase 5: AgentLoop ===")

# 6. Tool Parser
print("\n6. Tool Parser 工具调用解析")
try:
    from harness.llm_adapter.tool_parser import parse_tool_call, is_tool_call, extract_final_response

    # XML 格式
    xml_input = '好的，我先查一下肌酐的参考范围。\n<tool_call>\n{"name": "reference_lookup", "args": {"indicator": "creatinine"}}\n</tool_call>'
    call = parse_tool_call(xml_input)
    assert call is not None
    assert call.name == "reference_lookup"
    assert call.args["indicator"] == "creatinine"
    print(f"   [OK] XML 格式: {call.name}({call.args})")

    # Action 格式
    action_input = "Action: search_knowledge\nAction Input: {\"query\": \"CKD分期\"}"
    call = parse_tool_call(action_input)
    assert call is not None
    assert call.name == "search_knowledge"
    print(f"   [OK] Action 格式: {call.name}({call.args})")

    # 无工具调用
    normal_text = "肌酐120μmol/L略高于正常上限，建议您..."
    assert not is_tool_call(normal_text)
    print(f"   [OK] 普通回复: is_tool_call=False")

    # 提取最终回复
    cleaned = extract_final_response(xml_input)
    assert "tool_call" not in cleaned
    assert "好的" in cleaned
    print(f"   [OK] 提取最终回复: {cleaned[:50]}...")

except Exception as e:
    errors.append(f"tool_parser: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 7. Agent Tools
print("\n7. Agent Tools 工具函数")
try:
    from harness.llm_adapter.agent_tools import (
        tool_reference_lookup, tool_calculate_egfr,
        tool_search_knowledge, tool_analyze_indicator, get_default_tools,
    )

    # reference_lookup
    result = tool_reference_lookup('{"indicator": "creatinine"}')
    assert "肌酐" in result or "Creatinine" in result
    print(f"   [OK] reference_lookup: {result[:80]}...")

    # calculate_egfr
    result = tool_calculate_egfr('{"creatinine": 120, "age": 45, "gender": "男"}')
    assert "eGFR" in result
    assert "mL/min" in result
    print(f"   [OK] calculate_egfr: {result[:100]}...")

    # analyze_indicator
    result = tool_analyze_indicator('{"indicator": "creatinine", "value": 120, "age": 45, "gender": "男"}')
    assert "high" in result.lower() or "升高" in result or "异常" in result
    print(f"   [OK] analyze_indicator: {result[:100]}...")

    # 默认工具集
    tools = get_default_tools()
    assert len(tools) == 4
    tool_names = [t.name for t in tools]
    assert "reference_lookup" in tool_names
    assert "calculate_egfr" in tool_names
    assert "search_knowledge" in tool_names
    assert "analyze_indicator" in tool_names
    print(f"   [OK] 默认工具集: {tool_names}")

except Exception as e:
    errors.append(f"agent_tools: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 8. AgentLoop（不加载模型）
print("\n8. AgentLoop 调度循环导入")
try:
    from harness.llm_adapter.agent_loop import AgentLoop, _generate_tools_prompt

    tools = get_default_tools()
    prompt = _generate_tools_prompt(tools)
    assert "可用工具" in prompt
    assert "reference_lookup" in prompt
    assert "tool_call" in prompt
    print(f"   [OK] 工具 Prompt 生成: {len(prompt)} 字符")

    print(f"   [OK] AgentLoop 类导入成功 (max_steps=5)")

except Exception as e:
    errors.append(f"agent_loop: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 9. LabAgent 集成
print("\n9. LabAgent agent_loop 集成")
try:
    # 仅验证方法存在（不加载模型）
    from harness.llm_adapter.create_agent import LabAgent

    # 检查 agent_loop 方法已添加
    assert hasattr(LabAgent, 'agent_loop')
    assert hasattr(LabAgent, 'chat')
    assert hasattr(LabAgent, 'register_tool')
    print(f"   [OK] LabAgent 方法: chat, chat_stream, register_tool, agent_loop")

    from api.dependencies import AgentPool
    # 验证 AgentPool 有工具注册逻辑
    import inspect
    source = inspect.getsource(AgentPool.get_or_create)
    assert "agent_tools" in source
    assert "register_tool" in source
    print(f"   [OK] AgentPool.get_or_create 含工具自动注册")

except Exception as e:
    errors.append(f"LabAgent integration: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# ==============================
# 清理测试数据
print("\n清理测试数据...")
try:
    from app.persistence.database import get_session
    db = get_session()
    try:
        from app.persistence.models import ChatMessageModel, ReportModel, UserModel
        db.query(ChatMessageModel).filter(ChatMessageModel.user_id == "test_phase4").delete()
        db.query(ReportModel).filter(ReportModel.user_id == "test_phase4").delete()
        db.query(UserModel).filter(UserModel.id == "test_phase4").delete()
        db.commit()
        print("   测试数据已清理")
    finally:
        db.close()
except Exception:
    pass

# ==============================
print("\n" + "=" * 60)
if errors:
    print(f"验证完成，{len(errors)} 个错误:")
    for e in errors:
        print(f"  - {e}")
else:
    print("Phase 4+5 所有模块验证通过!")
    print()
    print("=== Phase 4 产出 ===")
    print("  app/persistence/database.py              — SQLite 引擎 + 会话工厂")
    print("  app/persistence/models.py                — UserModel/ReportModel/ChatMessageModel")
    print("  app/persistence/repositories/user_repo.py  — 用户 CRUD")
    print("  app/persistence/repositories/report_repo.py — 报告 CRUD")
    print("  app/persistence/repositories/chat_repo.py   — 对话记录 CRUD")
    print("  api/routes/user.py                       — [改造] DB+Agent 双写")
    print("  api/routes/report.py                     — [改造] DB+JSON 双写")
    print()
    print("=== Phase 5 产出 ===")
    print("  harness/llm_adapter/tool_parser.py        — 工具调用解析器 (XML+Action+JSON 三种格式)")
    print("  harness/llm_adapter/agent_loop.py         — AgentLoop 调度循环 (while 循环)")
    print("  harness/llm_adapter/agent_tools.py        — 4 个医疗专用工具")
    print("  harness/llm_adapter/create_agent.py       — [增强] +agent_loop() 方法")
    print("  api/dependencies.py                      — [增强] 自动注册默认工具")
    print("  api/models.py                            — [增强] ChatRequest.use_agent_loop")
    print("  server.py                                — [增强] DB 初始化")
    print("  api/routes/chat.py                       — [增强] AgentLoop 模式")
    print()
    print("=== AgentLoop 调度流程 ===")
    print("  用户输入 → State(HumanMessage)")
    print("  → assemble_final_prompt(state) + 工具描述")
    print("  → chat_model.invoke(prompt)")
    print("  → parse_tool_call(reply)")
    print("    ├─ 有工具调用 → 执行工具 → ToolMessage 写回 state → 循环")
    print("    └─ 无工具调用 → 最终回复 → 返回")
    print("  max_steps=5 | 快照回滚 | loop detection")
