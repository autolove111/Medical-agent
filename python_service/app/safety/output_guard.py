"""
安全红线 OutputGuard：可插拔规则引擎 + 输出净化管道

设计原则：
- 框架与规则分离：框架固定，具体红线规则通过配置注入
- 规则可插拔：每条规则是独立函数，注册/移除不影响其他规则
- 管道式处理：sanitize() 依次执行所有规则，收集命中信息
- 强制免责声明：在所有输出末尾注入

## 如何添加新规则

每条规则是 `(text: str) -> SafetyResult` 的可调用对象：

```python
from app.safety.output_guard import SafetyResult, RuleSeverity

def my_rule(text: str) -> SafetyResult:
    if "违规内容" in text:
        return SafetyResult(
            triggered=True,
            rule_name="my_rule",
            severity=RuleSeverity.BLOCK,
            message="检测到违规内容",
        )
    return SafetyResult(triggered=False)
```

然后注册到守卫：
```python
guard = get_output_guard()
guard.register(my_rule)
```

## 严重程度说明

- BLOCK:  完全阻断，返回固定安全回复
- WARN:   保留输出，但追加警告标记
- LOG:    仅记录日志，不改变输出
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import logging
import re

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = (
    "\n\n---\n"
    "⚠️ 本建议仅供临床参考，不构成诊断。最终诊断与治疗方案请以主治医生医嘱为准。\n"
    "如有不适请及时就医，勿因本建议延误病情。"
)


class RuleSeverity(str, Enum):
    """规则严重程度"""
    BLOCK = "block"     # 完全阻断，替换为安全回复
    WARN = "warn"       # 保留原文，追加警告
    LOG = "log"         # 仅记录，不干预


@dataclass
class SafetyResult:
    """单条规则的检查结果"""
    triggered: bool = False
    rule_name: str = ""
    severity: RuleSeverity = RuleSeverity.LOG
    message: str = ""
    matched_pattern: str = ""


@dataclass
class SafetyReport:
    """sanitize() 的完整安全报告"""
    original: str                           # 原始文本
    sanitized: str                          # 净化后文本
    is_safe: bool = True                    # 是否安全（无 BLOCK 触发）
    blocked: bool = False                   # 是否被完全阻断
    warnings: list[str] = field(default_factory=list)   # WARN 级别的提示
    triggered_rules: list[str] = field(default_factory=list)  # 触发规则名
    blocking_rules: list[str] = field(default_factory=list)   # 阻断规则名


# 规则类型：接收文本，返回 SafetyResult
SafetyRule = Callable[[str], SafetyResult]


class OutputGuard:
    """
    输出安全守卫：管理规则注册表 + 执行净化管道

    使用方式：
        guard = OutputGuard()
        guard.register_stub_rules()      # 注册默认桩规则
        report = guard.sanitize(reply)   # 净化输出
        final = guard.inject_disclaimer(report.sanitized)  # 注入免责声明
    """

    def __init__(self):
        self._rules: list[SafetyRule] = []
        self._disclaimer = DISCLAIMER_TEXT

    # ---- 规则管理 ----

    def register(self, rule: SafetyRule, priority: int = 0) -> None:
        """
        注册一条安全规则

        参数：
            rule:     规则函数 (text) -> SafetyResult
            priority: 优先级（越小越先执行，未使用则按注册顺序）
        """
        self._rules.append(rule)
        name = getattr(rule, "__name__", str(rule))
        logger.info("Safety rule registered: %s", name)

    def remove(self, rule_name: str) -> bool:
        """按函数名移除规则"""
        for i, rule in enumerate(self._rules):
            if getattr(rule, "__name__", "") == rule_name:
                self._rules.pop(i)
                logger.info("Safety rule removed: %s", rule_name)
                return True
        return False

    def clear(self) -> None:
        """清空所有规则"""
        self._rules.clear()

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ---- 核心管道 ----

    def sanitize(self, text: str) -> SafetyReport:
        """
        执行净化管道：依次运行所有规则

        BLOCK → 立即阻断返回安全回复
        WARN  → 应用文本修改（如截断话题标签），不阻断
        LOG   → 仅记录
        """
        report = SafetyReport(original=text, sanitized=text)

        if not text or not text.strip():
            return report

        for rule in self._rules:
            current = report.sanitized
            try:
                result = rule(current)
            except Exception as e:
                logger.error("Safety rule %s raised: %s",
                             getattr(rule, "__name__", str(rule)), e)
                continue

            if not result.triggered:
                continue

            report.triggered_rules.append(result.rule_name)

            if result.severity == RuleSeverity.BLOCK:
                report.blocked = True
                report.is_safe = False
                report.blocking_rules.append(result.rule_name)
                report.sanitized = self._block_response(result)
                logger.warning("BLOCKED by '%s': %s", result.rule_name, result.message)
                return report

            elif result.severity == RuleSeverity.WARN:
                # WARN 规则可修改文本
                if result.rule_name == "strip_hashtag_spam":
                    m = re.search(r'(\n*(?:#[一-鿿\w]+[\s#]*){5,}$)', current)
                    if m:
                        report.sanitized = current[:m.start()].rstrip()
                        report.warnings.append(
                            f"[{result.rule_name}] 截断 {len(current) - len(report.sanitized)} 字符话题标签"
                        )
                        logger.info("WARN: stripped hashtag spam (%d chars)",
                                    len(current) - len(report.sanitized))

            elif result.severity == RuleSeverity.LOG:
                logger.debug("LOG from '%s': %s", result.rule_name, result.message)

        return report

    def _block_response(self, result: SafetyResult) -> str:
        """生成阻断时的安全回复"""
        return (
            "抱歉，您的提问涉及我无法回答的内容。\n\n"
            "我是专业的医疗检验助手，可以提供：\n"
            "- 化验指标的通俗解读\n"
            "- 检验结果的参考范围分析\n"
            "- 饮食与运动方面的健康建议\n\n"
            "请提出与检验报告相关的问题，我会尽力为您解答。\n\n"
            + DISCLAIMER_TEXT
        )

    def inject_disclaimer(self, text: str) -> str:
        """在输出末尾注入免责声明（如文本中尚未包含）"""
        if "仅供临床参考" in text or "不构成诊断" in text:
            return text
        return text + self._disclaimer

    # ---- 默认桩规则（具体内容待后续填充） ----

    def register_stub_rules(self) -> None:
        """注册默认安全规则"""

        # 规则 0: 截断末尾话题标签泛滥（小模型常见问题）
        def rule_strip_hashtag_spam(text: str) -> SafetyResult:
            """截断回复末尾连续 5 个以上的 #话题标签"""
            # 匹配末尾连续 #中文标签 模式
            m = re.search(r'(\n*(?:#\w+[\s#]*){5,}$)', text)
            if m:
                truncated = text[:m.start()].rstrip()
                return SafetyResult(
                    triggered=True,
                    rule_name="strip_hashtag_spam",
                    severity=RuleSeverity.WARN,
                    message=f"截断了 {len(text) - len(truncated)} 字符的话题标签",
                    matched_pattern=m.group()[:50],
                )
            return SafetyResult(triggered=False)

        # 规则 0b: WARN 规则执行文本修改
        def _apply_warn_rule(text: str, rule_name: str) -> str:
            if rule_name == "strip_hashtag_spam":
                m = re.search(r'(\n*(?:#\w+[\s#]*){5,}$)', text)
                if m:
                    return text[:m.start()].rstrip()
            return text

        # 桩规则 1: 禁止确诊 — 待填充
        def stub_no_diagnosis(text: str) -> SafetyResult:
            """TODO: 检测确定诊断性断言"""
            return SafetyResult(triggered=False)

        # 桩规则 2: 禁止处方 — 待填充
        def stub_no_prescription(text: str) -> SafetyResult:
            """TODO: 检测药品品牌/剂量推荐"""
            return SafetyResult(triggered=False)

        # 桩规则 3: 禁止改写数据 — 待填充
        def stub_no_data_modification(text: str) -> SafetyResult:
            """TODO: 检测对原始检验数据的改写意图"""
            return SafetyResult(triggered=False)

        self.register(rule_strip_hashtag_spam)
        self.register(stub_no_diagnosis)
        self.register(stub_no_prescription)
        self.register(stub_no_data_modification)
        logger.info("Registered 4 safety rules (1 active + 3 stubs)")


# ---- 全局单例 ----

_guard: Optional[OutputGuard] = None


def get_output_guard() -> OutputGuard:
    """获取 OutputGuard 全局单例"""
    global _guard
    if _guard is None:
        _guard = OutputGuard()
        _guard.register_stub_rules()
    return _guard
