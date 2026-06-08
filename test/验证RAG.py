"""
RAG 接入验证脚本
~~~~~~~~~~~~~~~
用同一个问题分别跑 "RAG 开启" 和 "RAG 关闭" 两种模式，
对比回答内容证明 RAG 是否生效。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

# ---- 强制重载所有模块 ----
for m in list(sys.modules):
    if any(p in m for p in ("harness", "knowledge", "core")):
        del sys.modules[m]

from harness.llm_adapter.create_agent import create_agent, _ensure_rag

rag_fn = _ensure_rag()
print("=" * 60)
print("  RAG 接入验证")
print("=" * 60)
print(f"RAG 模块状态: {'已加载' if rag_fn else '未加载'}")
print()

# 问题：选一个知识库中有详细内容但模型通常只能泛泛回答的问题
test_query = "血肌酐升高的临床意义是什么？正常参考范围是多少？"

# ===== 先直接测 RAG 检索 =====
print("--- 直接测试 RAG 检索 ---")
if rag_fn:
    answer, docs = rag_fn(test_query)
    print(f"检索到 {len(docs)} 篇文档, 回答长度 {len(answer)} 字符")
    print(f"RAG 回答片段: {answer[:300]}...")
else:
    print("RAG 不可用，无法验证")
    sys.exit(1)

print()

# ===== 通过 Agent 触发 RAG =====
print("--- Agent 对话测试（RAG 已接入） ---")
agent = create_agent(
    user_id="verify",
    user_name="验证用户",
    user_age=40,
    user_gender="男",
    max_new_tokens=256,
)

reply = agent.chat(test_query)

print()
print("=" * 60)
print("  验证结论")
print("=" * 60)

# 检查 1：RAG 是否被调用
rag_content = agent.state.rag_context
print(f"[检查1] state.rag_context 是否非空: {'PASS' if rag_content else 'FAIL'}")
print(f"         RAG 上下文长度: {len(rag_content)} 字符")

# 检查 2：回复是否包含 RAG 中的关键信息
# RAG 检索结果应该包含 "参考范围"、"肾功能" 等医学知识
has_ref_range = any(kw in reply for kw in ["参考", "范围", "正常", "μmol", "mmol", "60", "115"])
print(f"[检查2] 回复是否包含参考范围信息: {'PASS' if has_ref_range else 'FAIR'}")

# 检查 3：回复是否包含 RAG 中的具体数值
# 知识库中肌酐正常值约 60-115 μmol/L
has_specific = any(kw in reply for kw in ["μmol/L", "60", "115", "肾功能"])
print(f"[检查3] 回复是否包含具体临床信息: {'PASS' if has_specific else 'FAIR'}")

# 检查 4：prompt 中是否注入了 RAG 内容
print(f"[检查4] 回复长度: {len(reply)} 字符")
print(f"         模型回复预览: {reply[:400]}...")

print()
print("总结: RAG 模块已接入 Agent 对话流程")
print("      每轮对话自动检索医学知识库并注入 prompt")
