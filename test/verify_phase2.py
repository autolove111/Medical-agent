"""验证 Phase 2：报告处理管线端到端"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'python_service'))

errors = []

print("=" * 60)
print("Phase 2 验证：报告管线 + 指标分类 + 联动引擎")
print("=" * 60)

# 1. LabReport 数据模型
print("\n1. LabReport / LabIndicator 数据模型")
try:
    from app.business.lab_report import LabReport, LabIndicator
    ind = LabIndicator(
        key="creatinine", name="血肌酐", value=120.0,
        unit="μmol/L", ref_range="60-115 μmol/L",
        status="high", description="肾功能主要标志", is_critical=False,
    )
    assert ind.value == 120.0
    text = ind.to_context_text()
    assert "血肌酐" in text
    assert "120" in text
    print(f"   [OK] LabIndicator 创建 + to_context_text: {text[:60]}...")

    report = LabReport(
        report_id="rpt_test_001", user_id="u001",
        report_date="2026-05-26",
    )
    report.indicators.append(ind)
    report.abnormal_indicators.append(ind)
    assert report.total_count == 1
    assert report.abnormal_count == 1
    ctx = report.to_context_text()
    assert "异常指标" in ctx
    print(f"   [OK] LabReport 创建 + to_context_text: {len(ctx)} 字符")
except Exception as e:
    errors.append(f"LabReport: {e}")
    print(f"   [FAIL] {e}")

# 2. 指标分类器（对接完整 reference_ranges）
print("\n2. 指标分类器 batch_classify（40+ 参考范围 + 年龄/性别分层）")
try:
    from app.business.indicator_classifier import batch_classify, classify_indicator

    # 测试基础分类
    result = classify_indicator("creatinine", 120, age=45, gender="男")
    assert result["status"] == "high"
    assert "μmol/L" in result["unit"]
    print(f"   [OK] 肌酐 120（男45岁）→ status={result['status']}, ref={result['ref_range']}")

    result = classify_indicator("creatinine", 85, age=25, gender="女")
    assert result["status"] == "normal"
    print(f"   [OK] 肌酐 85（女25岁）→ status={result['status']}")

    # 测试危急值
    result = classify_indicator("creatinine", 550, age=45, gender="男")
    assert result["status"] == "critical_high"
    assert result["is_critical"] == True
    print(f"   [OK] 肌酐 550 → status={result['status']}, is_critical={result['is_critical']}")

    # 测试批量分类
    patient_labs = {
        "creatinine": 120, "bun": 9.5, "glucose": 7.0,
        "hemoglobin": 110, "alt": 35, "wbc": 8.0,
    }
    results = batch_classify(patient_labs, age=45, gender="男")
    statuses = {r["key"]: r["status"] for r in results}
    assert statuses["creatinine"] == "high"
    assert statuses["bun"] == "high"
    assert statuses["glucose"] == "high"
    print(f"   [OK] 批量分类 6 项: {statuses}")
except Exception as e:
    errors.append(f"indicator_classifier: {e}")
    print(f"   [FAIL] {e}")

# 3. 联动规则引擎
print("\n3. 联动规则引擎 CorrelationEngine")
try:
    from app.business.correlation_engine import CorrelationEngine
    engine = CorrelationEngine()

    # 模拟肾功能异常指标
    indicators = [
        {"key": "creatinine", "name": "血肌酐", "status": "high"},
        {"key": "bun", "name": "尿素氮", "status": "high"},
        {"key": "glucose", "name": "血糖", "status": "normal"},
    ]
    matches = engine.analyze(indicators)
    assert len(matches) >= 1
    assert matches[0].name == "肾功能受损信号"
    assert matches[0].severity == "high"
    print(f"   [OK] 肾功能异常 → {len(matches)} 条匹配: {[m.name for m in matches]}")

    # 测试无匹配
    indicators_normal = [
        {"key": "wbc", "name": "白细胞", "status": "normal"},
        {"key": "glucose", "name": "血糖", "status": "normal"},
    ]
    matches = engine.analyze(indicators_normal)
    assert len(matches) == 0
    print(f"   [OK] 全部正常 → {len(matches)} 条匹配")

    # 测试多模式
    indicators_multi = [
        {"key": "alt", "name": "ALT", "status": "high"},
        {"key": "ast", "name": "AST", "status": "high"},
        {"key": "creatinine", "name": "肌酐", "status": "high"},
        {"key": "bun", "name": "尿素氮", "status": "high"},
        {"key": "glucose", "name": "血糖", "status": "high"},
        {"key": "cholesterol", "name": "胆固醇", "status": "high"},
        {"key": "triglyceride", "name": "甘油三酯", "status": "high"},
    ]
    matches = engine.analyze(indicators_multi)
    assert len(matches) >= 3
    names = [m.name for m in matches]
    assert "肝细胞损伤信号" in names
    assert "肾功能受损信号" in names
    assert "代谢综合征（三高倾向）" in names
    print(f"   [OK] 复合异常 → {len(matches)} 条匹配: {names}")

    # 测试 prompt 生成
    ctx = engine.to_prompt_context(matches)
    assert "多指标联动分析" in ctx
    print(f"   [OK] 联动 prompt 生成: {len(ctx)} 字符")

except Exception as e:
    errors.append(f"correlation_engine: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 4. ReportPipeline（不含 OCR 调用）
print("\n4. ReportPipeline 报告构建")
try:
    from app.business.report_pipeline import ReportPipeline, get_report_pipeline
    pipeline = ReportPipeline()

    # 模拟 OCR 结果
    mock_ocr = {
        "gat_structured": {
            "patient_labs": {
                "creatinine": 130, "bun": 9.5, "glucose": 7.2,
                "hemoglobin": 105, "wbc": 12.0, "ne": 78,
            }
        },
        "full_extraction": ["肌酐: 130 μmol/L", "尿素氮: 9.5 mmol/L"],
    }

    report = pipeline.build_report(
        user_id="test_user",
        file_path="/tmp/test.jpg",
        ocr_result=mock_ocr,
        report_date="2026-05-26",
        age=50,
        gender="男",
    )
    assert report.total_count == 6
    assert report.abnormal_count >= 3  # 肌酐↑, 尿素氮↑, 血糖↑, 血红蛋白↓, 白细胞↑, 中性粒↑
    print(f"   [OK] 报告构建: {report.total_count} 项, {report.abnormal_count} 异常")

    # 联动分析
    corr = pipeline.analyze_correlations(report)
    matches = corr["matches"]
    match_names = [m.name for m in matches]
    print(f"   [OK] 联动分析: {len(matches)} 条 ({match_names})")

    # 解读 prompt
    prompt = pipeline.generate_interpretation_prompt(report, corr)
    assert "智能解读" in prompt
    assert "总览" in prompt
    print(f"   [OK] 解读 prompt: {len(prompt)} 字符")

    # 保存 + 加载
    path = pipeline.save_report(report)
    loaded = pipeline.load_report(report.report_id)
    assert loaded is not None
    assert loaded.total_count == report.total_count
    print(f"   [OK] 报告持久化: save → load OK")

except Exception as e:
    errors.append(f"ReportPipeline: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 5. 路由层
print("\n5. API 路由导入验证")
try:
    from api.routes.report import router as report_router, get_report, set_report
    from api.routes.chat import router as chat_router, _build_report_context
    print(f"   [OK] report router: prefix={report_router.prefix}")
    print(f"   [OK] chat router: prefix={chat_router.prefix}")

    # 验证 _build_report_context 对不存在的报告优雅降级
    ctx = _build_report_context("nonexistent")
    assert "未找到" in ctx
    print(f"   [OK] 缺失报告降级: {ctx[:50]}...")
except Exception as e:
    errors.append(f"Routes: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# === 结果 ===
print("\n" + "=" * 60)
if errors:
    print(f"Phase 2 验证完成，{len(errors)} 个错误:")
    for e in errors:
        print(f"  - {e}")
else:
    print("Phase 2 所有模块验证通过!")
    print()
    print("新增文件清单：")
    print("  app/business/lab_report.py           — 检验报告数据模型")
    print("  app/business/indicator_classifier.py  — 40+ 指标分类器")
    print("  app/business/correlation_engine.py   — 15 组联动规则引擎")
    print("  app/business/report_pipeline.py      — 报告处理管线")
    print("  api/routes/report.py                 — [重写] 接入完整管线")
    print("  api/routes/chat.py                   — [增强] 报告上下文注入")
