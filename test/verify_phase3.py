"""验证 Phase 3：解读引擎 + 来源引用 + 饮食运动建议"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'python_service'))

errors = []

print("=" * 60)
print("Phase 3 验证：解读引擎 + 来源引用 + 饮食运动")
print("=" * 60)

# 1. SourceTracker
print("\n1. SourceTracker 来源追踪器")
try:
    from app.business.source_tracker import SourceTracker, Citation

    tracker = SourceTracker()
    assert tracker.source_count == 0

    # 模拟 RAG docs
    class MockDoc:
        def __init__(self, content, source):
            self.page_content = content
            self.metadata = {"source": source}

    docs = [
        MockDoc("## 慢性肾脏病饮食管理\n肌酐是肾功能主要标志...", "肾脏医学指南.txt"),
        MockDoc("## 肾病营养原则\n每日蛋白质摄入建议 0.6-0.8 g/kg...", "临床营养学.txt"),
    ]
    n = tracker.add_from_rag_docs(docs, category="indicator", indicator_keys=["creatinine", "bun"])
    assert n == 2
    assert tracker.source_count == 2
    print(f"   [OK] 添加 2 条 RAG 来源: {tracker.unique_sources}")

    # 手动添加
    tracker.add_manual("内置循证规则", "肾功能下降时建议优质低蛋白饮食...", category="diet", indicator_keys=["creatinine"])
    assert tracker.source_count == 3
    print(f"   [OK] 手动添加 1 条: total={tracker.source_count}")

    # 按类别过滤
    diet = tracker.get_by_category("diet")
    assert len(diet) == 1
    print(f"   [OK] diet 类别: {len(diet)} 条")

    # Prompt block
    block = tracker.to_prompt_block()
    assert "知识库来源引用" in block
    assert "肾脏医学指南" in block
    print(f"   [OK] prompt block: {len(block)} 字符")

    # API list
    api_list = tracker.to_api_list()
    assert len(api_list) == 3
    for item in api_list:
        assert "source" in item and "excerpt" in item and "category" in item
    print(f"   [OK] API list: {len(api_list)} 项")
except Exception as e:
    errors.append(f"SourceTracker: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 2. DietaryAdvisor
print("\n2. DietaryAdvisor 饮食运动顾问")
try:
    from app.business.dietary_advisor import DietaryAdvisor

    advisor = DietaryAdvisor()

    # 肾功能异常
    advice = advisor.get_advice_for_indicators(["creatinine", "uric_acid"])
    assert len(advice) >= 4  # 至少4条（低蛋白+低盐+运动+低嘌呤+饮水）
    categories = {}
    for a in advice:
        categories[a.category] = categories.get(a.category, 0) + 1
    print(f"   [OK] 肾功能异常建议: {len(advice)} 条 (diet={categories.get('diet', 0)}, exercise={categories.get('exercise', 0)})")

    # 血糖异常
    advice = advisor.get_advice_for_indicators(["glucose"])
    assert len(advice) >= 2
    print(f"   [OK] 血糖异常建议: {len(advice)} 条")

    # 多指标混合
    advice = advisor.get_advice_for_indicators(["creatinine", "glucose", "cholesterol", "alt"])
    assert len(advice) >= 6
    # 验证去重
    titles = [a.title for a in advice]
    assert len(titles) == len(set(titles)), "存在重复建议"
    print(f"   [OK] 多指标混合: {len(advice)} 条（已去重）")

    # 饮食段生成
    diet_block = advisor.generate_diet_section(["creatinine", "glucose", "alt"])
    assert "饮食建议" in diet_block
    assert len(diet_block) > 100
    print(f"   [OK] diet_block: {len(diet_block)} 字符")

    # 运动段生成
    exercise_block = advisor.generate_exercise_section(["creatinine", "glucose"])
    assert "运动建议" in exercise_block
    print(f"   [OK] exercise_block: {len(exercise_block)} 字符")

except Exception as e:
    errors.append(f"DietaryAdvisor: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 3. InterpretationEngine
print("\n3. InterpretationEngine 解读引擎")
try:
    from app.business.interpretation_engine import InterpretationEngine, get_interpretation_engine
    from app.business.lab_report import LabReport, LabIndicator

    engine = InterpretationEngine()

    # 构建模拟报告
    report = LabReport(
        report_id="rpt_test_phase3",
        user_id="u001",
        report_date="2026-05-26",
    )
    indicators = [
        LabIndicator(key="creatinine", name="血肌酐", value=130.0, unit="μmol/L",
                     ref_range="60-115 μmol/L", status="high", description="肾功能主要标志"),
        LabIndicator(key="bun", name="尿素氮", value=9.5, unit="mmol/L",
                     ref_range="2.5-8.0 mmol/L", status="high", description="肾脏清除功能标志"),
        LabIndicator(key="glucose", name="血糖", value=7.2, unit="mmol/L",
                     ref_range="3.9-6.0 mmol/L", status="high", description="能量代谢标志"),
        LabIndicator(key="alt", name="ALT", value=35, unit="U/L",
                     ref_range="<40 U/L", status="normal", description="肝脏损伤标志"),
        LabIndicator(key="hemoglobin", name="血红蛋白", value=105, unit="g/L",
                     ref_range="115-175 g/L", status="low", description="携氧蛋白质"),
        LabIndicator(key="cholesterol", name="总胆固醇", value=5.8, unit="mmol/L",
                     ref_range="<5.2 mmol/L", status="high", description="脂质代谢指标"),
    ]
    for ind in indicators:
        report.indicators.append(ind)
        if ind.status != "normal":
            report.abnormal_indicators.append(ind)
        else:
            report.normal_indicators.append(ind)

    print(f"   [OK] 报告: {report.total_count} 项, {report.abnormal_count} 异常")

    # 构建解读 prompt
    result = engine.build_interpretation_prompt(report=report, rag_answer="", rag_docs=None)

    assert result["abnormal_count"] == 5  # 肌酐+尿素氮+血糖+血红蛋白+胆固醇
    assert result["correlation_count"] >= 2  # 肾功能受损 + 肾性贫血 + 代谢综合征等
    assert len(result["prompt"]) > 500
    print(f"   [OK] prompt: {len(result['prompt'])} 字符")
    print(f"   [OK] 联动匹配: {result['correlation_count']} 条")
    print(f"   [OK] 来源引用: {result['total_sources']} 条, 唯一来源: {result['unique_sources']}")

    # 验证 prompt 包含关键结构
    assert "报告总览" in result["prompt"]
    assert "异常指标逐项解读" in result["prompt"]
    assert "关联分析" in result["prompt"]
    assert "健康管理建议" in result["prompt"]
    assert "参考来源" in result["prompt"]
    assert "免责声明" in result["prompt"]
    print(f"   [OK] prompt 包含 6 个必要章节")

    # 验证饮食/运动块
    assert len(result["diet_block"]) > 100
    assert len(result["exercise_block"]) > 50
    print(f"   [OK] diet_block={len(result['diet_block'])} 字符, exercise_block={len(result['exercise_block'])} 字符")

    # 验证来源列表
    assert len(result["sources"]) > 0
    for s in result["sources"]:
        assert "source" in s and "category" in s
    print(f"   [OK] sources API list: {len(result['sources'])} 项")

    # 单例
    engine2 = get_interpretation_engine()
    assert engine2 is get_interpretation_engine()
    print(f"   [OK] 单例模式正常")

except Exception as e:
    errors.append(f"InterpretationEngine: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 4. RAG Formatter 增强
print("\n4. RAG Formatter extract_source_metadata")
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service',
                                     'harness', 'long_memory'))
    from knowledge.rag_formatter import extract_source_metadata

    class MockDoc2:
        def __init__(self, content, source):
            self.page_content = content
            self.metadata = {"source": source}

    docs = [
        MockDoc2("## 肾功能评估\n肌酐是评估肾小球滤过功能的核心指标...", "检验医学指南.txt"),
        MockDoc2("## 糖尿病管理\n血糖控制目标：空腹 3.9-6.0 mmol/L...", "内分泌学指南.txt"),
    ]
    sources = extract_source_metadata(docs)
    assert len(sources) == 2
    assert sources[0]["source"] == "检验医学指南.txt"
    assert sources[0]["section"] == "肾功能评估"
    assert len(sources[1]["excerpt"]) > 0
    print(f"   [OK] 提取 2 条结构化来源: section={sources[0]['section']}, {sources[1]['section']}")
except Exception as e:
    errors.append(f"RAG Formatter: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 5. API 路由
print("\n5. API 路由导入验证")
try:
    from api.models import ChatResponse, SourceItem
    # 验证新模型
    src = SourceItem(source="test.txt", section="test", excerpt="test", category="rag")
    resp = ChatResponse(reply="test", sources=["test.txt"], source_details=[src], turn_count=1)
    d = resp.model_dump()
    assert "source_details" in d
    assert len(d["source_details"]) == 1
    print(f"   [OK] ChatResponse 含 source_details: {len(d['source_details'])} 项")

    from api.routes.chat import router, get_latest_sources, _build_report_context
    assert router.prefix == "/api"
    print(f"   [OK] chat router OK, prefix={router.prefix}")

    # 验证 _build_report_context 降级
    ctx, sources = _build_report_context("nonexistent_report")
    assert "未找到" in ctx
    assert sources == []
    print(f"   [OK] 降级: ctx 含'未找到', sources=[]")
except Exception as e:
    errors.append(f"Routes: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# === 结果 ===
print("\n" + "=" * 60)
if errors:
    print(f"Phase 3 验证完成，{len(errors)} 个错误:")
    for e in errors:
        print(f"  - {e}")
else:
    print("Phase 3 所有模块验证通过!")
    print()
    print("新增/修改文件清单：")
    print("  app/business/source_tracker.py        — 来源追踪器（Citation/SourceTracker）")
    print("  app/business/dietary_advisor.py       — 饮食运动顾问（10+ 类指标循证规则）")
    print("  app/business/interpretation_engine.py — 解读引擎（6段式结构化 Prompt）")
    print("  harness/.../rag_formatter.py          — [增强] extract_source_metadata()")
    print("  api/models.py                         — [增强] SourceItem + ChatResponse.source_details")
    print("  api/routes/chat.py                    — [增强] InterpretationEngine 集成 + GET /chat/sources")
