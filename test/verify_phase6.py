"""验证 Phase 6: 安全红线 OutputGuard 框架"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_service'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'python_service'))

print("=" * 60)
print("Phase 6 验证: OutputGuard 安全红线框架")
print("=" * 60)

errors = []

# 1. 框架导入
print("\n1. OutputGuard 框架导入")
try:
    from app.safety.output_guard import (
        OutputGuard, SafetyResult, SafetyReport, RuleSeverity,
        DISCLAIMER_TEXT, get_output_guard,
    )
    print("   [OK] 所有类/常量导入成功")
except Exception as e:
    errors.append(f"import: {e}")
    print(f"   [FAIL] {e}")

# 2. RuleSeverity
print("\n2. RuleSeverity 枚举")
try:
    assert RuleSeverity.BLOCK == "block"
    assert RuleSeverity.WARN == "warn"
    assert RuleSeverity.LOG == "log"
    print("   [OK] BLOCK/WARN/LOG 三个级别")
except Exception as e:
    errors.append(f"severity: {e}")
    print(f"   [FAIL] {e}")

# 3. SafetyResult
print("\n3. SafetyResult 数据类")
try:
    r = SafetyResult(triggered=True, rule_name="test", severity=RuleSeverity.WARN, message="test msg")
    assert r.triggered
    assert r.rule_name == "test"
    print("   [OK] SafetyResult 创建正常")
except Exception as e:
    errors.append(f"result: {e}")
    print(f"   [FAIL] {e}")

# 4. 规则注册/移除
print("\n4. 规则注册与移除")
try:
    guard = OutputGuard()
    assert guard.rule_count == 0

    def my_rule(text):
        return SafetyResult(triggered=False)

    guard.register(my_rule)
    assert guard.rule_count == 1
    print("   [OK] 注册规则: count=1")

    guard.remove("my_rule")
    assert guard.rule_count == 0
    print("   [OK] 移除规则: count=0")

    guard.clear()
    assert guard.rule_count == 0
    print("   [OK] 清空规则: count=0")
except Exception as e:
    errors.append(f"register: {e}")
    print(f"   [FAIL] {e}")

# 5. sanitize 管道
print("\n5. sanitize 净化管道")
try:
    guard = OutputGuard()

    # 无规则时
    report = guard.sanitize("测试文本")
    assert report.sanitized == "测试文本"
    assert report.is_safe
    print("   [OK] 无规则: 原文通过")

    # BLOCK 规则
    guard.clear()
    def block_rule(text):
        if "确诊" in text:
            return SafetyResult(triggered=True, rule_name="block_test", severity=RuleSeverity.BLOCK, message="包含确诊")
        return SafetyResult(triggered=False)
    guard.register(block_rule)

    report = guard.sanitize("您已确诊糖尿病")
    assert report.blocked
    assert "抱歉" in report.sanitized
    assert not report.is_safe
    print("   [OK] BLOCK 规则: 触发阻止, 返回安全回复")

    report2 = guard.sanitize("肌酐120是正常的吗")
    assert not report2.blocked
    assert report2.sanitized == "肌酐120是正常的吗"
    print("   [OK] BLOCK 规则: 正常内容通过")

    # WARN 规则
    guard.clear()
    def warn_rule(text):
        if "建议服用" in text:
            return SafetyResult(triggered=True, rule_name="warn_test", severity=RuleSeverity.WARN, message="可能涉及用药建议")
        return SafetyResult(triggered=False)
    guard.register(warn_rule)

    report = guard.sanitize("我建议您多喝水")
    assert not report.blocked
    assert len(report.warnings) == 0
    print("   [OK] WARN 规则: 安全内容无警告")

    report = guard.sanitize("我建议服用药物A")
    assert not report.blocked  # WARN 不阻止
    assert len(report.warnings) == 1
    print(f"   [OK] WARN 规则: 警告数={len(report.warnings)}, 原文保留")

except Exception as e:
    errors.append(f"sanitize: {e}")
    import traceback; traceback.print_exc()
    print(f"   [FAIL] {e}")

# 6. 免责声明注入
print("\n6. 免责声明注入")
try:
    guard = OutputGuard()

    text = "肌酐120是正常的"
    injected = guard.inject_disclaimer(text)
    assert "仅供临床参考" in injected
    assert "不构成诊断" in injected
    print(f"   [OK] 免责声明注入: {len(injected)} 字符")

    # 已含声明不重复注入
    text2 = "肌酐120偏高，本建议仅供临床参考。"
    injected2 = guard.inject_disclaimer(text2)
    assert injected2 == text2  # 不重复
    print(f"   [OK] 重复注入保护: 已含声明则跳过")

except Exception as e:
    errors.append(f"disclaimer: {e}")
    print(f"   [FAIL] {e}")

# 7. 默认桩规则
print("\n7. 默认桩规则注册")
try:
    guard = OutputGuard()
    guard.register_stub_rules()
    assert guard.rule_count == 3
    print(f"   [OK] 注册 3 条桩规则: count={guard.rule_count}")

    # 验证桩规则不影响正常文本
    report = guard.sanitize("肌酐120μmol/L属于正常范围")
    assert not report.blocked
    assert report.is_safe
    print("   [OK] 桩规则不误伤正常文本")
except Exception as e:
    errors.append(f"stub: {e}")
    print(f"   [FAIL] {e}")

# 8. 全局单例
print("\n8. 全局单例")
try:
    g1 = get_output_guard()
    g2 = get_output_guard()
    assert g1 is g2
    print(f"   [OK] 单例模式: {g2.rule_count} 条规则")
except Exception as e:
    errors.append(f"singleton: {e}")
    print(f"   [FAIL] {e}")

# 9. LabAgent 集成（仅检查方法存在，不加载模型）
print("\n9. LabAgent _safety_check 方法")
try:
    from harness.llm_adapter.create_agent import LabAgent
    assert hasattr(LabAgent, '_safety_check')
    print("   [OK] LabAgent._safety_check 方法已添加")
except Exception as e:
    errors.append(f"integration: {e}")
    print(f"   [FAIL] {e}")

# =====
print("\n" + "=" * 60)
if errors:
    print(f"Phase 6 验证完成，{len(errors)} 个错误:")
    for e in errors:
        print(f"  - {e}")
else:
    print("Phase 6 所有验证通过!")
    print()
    print("产出:")
    print("  app/safety/output_guard.py  — OutputGuard 可插拔规则引擎")
    print("    - RuleSeverity: BLOCK / WARN / LOG 三级")
    print("    - SafetyRule: (text) -> SafetyResult 类型协议")
    print("    - register/remove/clear 规则管理")
    print("    - sanitize() 管道: 依次执行规则, BLOCK 立即终止")
    print("    - inject_disclaimer() 强制免责声明")
    print("    - 3 条桩规则 (stub_no_diagnosis/stub_no_prescription/stub_no_data_modification)")
    print("    - 全局单例 get_output_guard()")
    print("  harness/llm_adapter/create_agent.py — [集成] _safety_check()")
    print("    - chat() 回复前执行 sanitize + inject_disclaimer")
    print("    - chat_stream() 完整回复后执行安全检测")
