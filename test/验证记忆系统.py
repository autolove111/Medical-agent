"""
记忆系统验证脚本
~~~~~~~~~~~~~~~~
验证 STM（短期记忆）和 LTM（长期记忆）是否正常工作。

运行方式：
    cd python_service
    python ../test/验证记忆系统.py

注意：LTM 测试使用独立 SQLite 测试库，不影响生产 PostgreSQL。
"""

import sys
import os
import shutil
import tempfile

# 确保 python_service 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

# 清除旧模块缓存
for m in list(sys.modules):
    if any(p in m for p in ("harness", "memory", "app.persistence", "core")):
        del sys.modules[m]


def _create_test_ltm():
    """创建使用 SQLite 测试库的 LTMManager（通过环境变量切换数据库）"""
    # 设置测试数据库 URL（必须在导入 database 模块之前）
    tmp_db = tempfile.mktemp(suffix=".db")
    test_url = f"sqlite:///{tmp_db}"
    os.environ["DATABASE_URL"] = test_url

    # 清除已加载的 database 模块，强制重新初始化
    for m in list(sys.modules):
        if "app.persistence" in m or "core.config" in m:
            del sys.modules[m]

    from app.persistence.database import SessionLocal, init_db
    init_db()

    db = SessionLocal()
    from harness.memory.ltm import LTMManager
    ltm = LTMManager(db=db)
    return ltm, db, tmp_db


# ============================================================
# 测试 1: STM 基本读写
# ============================================================

def test_stm_basic():
    """验证 STMManager 能添加消息、查询消息、统计 token"""
    from harness.memory.stm import STMManager

    print("=" * 60)
    print("  测试 1: STM 基本读写")
    print("=" * 60)

    stm = STMManager(session_id="test_session", user_id="u001", redis_client=None)

    stm.add_message("user", "我最近总是头晕，血红蛋白偏低怎么办？")
    stm.add_message("assistant", "血红蛋白偏低可能有多种原因，建议进一步检查...")
    stm.add_message("user", "我还有糖尿病史，需要注意什么？")
    stm.add_message("assistant", "糖尿病患者出现贫血需要特别关注肾功能...")

    all_msgs = stm.get_all_messages()
    recent_msgs = stm.get_recent_messages(n=2)

    print(f"  消息总数: {len(all_msgs)} (期望: 4)")
    print(f"  最近2轮: {len(recent_msgs)} 条 (期望: 4)")
    print(f"  缓冲区 token 数: {stm.conversation_buffer.total_tokens}")

    ok = len(all_msgs) == 4 and len(recent_msgs) == 4
    print(f"  结果: {'PASS' if ok else 'FAIL'}")
    print()
    return ok


# ============================================================
# 测试 2: STM 自动压缩
# ============================================================

def test_stm_compression():
    """验证 STM 超过 token 上限时滑动窗口压缩"""
    from harness.memory.stm import STMManager

    print("=" * 60)
    print("  测试 2: STM 滑动窗口压缩")
    print("=" * 60)

    # 设置小上限方便触发压缩（保留最近2轮，上限200 token）
    stm = STMManager(
        session_id="test_compress", user_id="u002",
        redis_client=None, max_tokens=200, keep_rounds=2,
    )

    # 添加足够多消息触发压缩
    for i in range(8):
        stm.add_message("user", f"第{i+1}个问题，关于肾脏功能检查指标肌酐尿素氮eGFR等的详细解释？")
        stm.add_message("assistant", f"关于第{i+1}个问题，肾脏功能检查主要包括肌酐Cr是肌肉代谢产物尿素氮BUN是蛋白质代谢终产物eGFR是评估肾小球滤过功能的重要指标...")

    buffer = stm.conversation_buffer
    has_summary = bool(buffer.summary)
    within_limit = buffer.total_tokens <= buffer.max_tokens * 1.5  # 允许一定余量
    recent_kept = len(buffer.messages) <= 2 * 2 + 2  # keep_rounds * 2 + 余量

    print(f"  消息数: {len(buffer.messages)}")
    print(f"  有摘要: {has_summary}")
    print(f"  摘要内容: {buffer.summary[:80]}..." if buffer.summary else "  摘要内容: (空)")
    print(f"  Token: {buffer.total_tokens}/{buffer.max_tokens}")
    print(f"  保留最近消息数: {'PASS' if recent_kept else 'FAIL'}")
    print(f"  结果: {'PASS' if has_summary else 'FAIL'}")
    print()
    return has_summary


# ============================================================
# 测试 3: LTM 读写（PostgreSQL / SQLite 测试库）
# ============================================================

def test_ltm():
    """验证 LTMManager 能通过 PostgreSQL 保存和读取长期记忆数据"""
    from harness.memory.models.user_profile import UserProfile
    from harness.memory.models.timeline_event import TimelineEvent, EventType
    from harness.memory.models.conversation_message import ConversationMessage
    from harness.memory.models.session_summary import SessionSummary

    print("=" * 60)
    print("  测试 3: LTM 读写 (DB)")
    print("=" * 60)

    ltm, db, tmp_db = _create_test_ltm()

    try:
        # 3a. 用户画像
        profile = UserProfile(
            user_id="u001", name="张三", age=45, gender="男",
            chronic_diseases=["糖尿病", "高血压"], allergies=["青霉素"],
        )
        ltm.save_user_profile(profile)
        loaded = ltm.get_user_profile("u001")

        profile_ok = (
            loaded is not None
            and loaded.name == "张三"
            and loaded.age == 45
            and "糖尿病" in loaded.chronic_diseases
        )
        print(f"  3a 用户画像: {'PASS' if profile_ok else 'FAIL'}")

        # 3b. 时间轴事件
        event = TimelineEvent(
            user_id="u001", session_id="s001",
            event_type=EventType.LAB_RESULT,
            content="肌酐 120 μmol/L，偏高",
            structured_data={"indicator": "Cr", "value": 120},
        )
        ltm.add_event(event)
        events = ltm.get_events("u001", event_type=EventType.LAB_RESULT)

        event_ok = len(events) == 1 and "肌酐" in events[0].content
        print(f"  3b 时间轴事件: {'PASS' if event_ok else 'FAIL'}")

        # 3c. 对话原文
        messages = [
            ConversationMessage(user_id="u001", session_id="s001", turn_number=1, role="user", content="肌酐偏高怎么办？"),
            ConversationMessage(user_id="u001", session_id="s001", turn_number=1, role="assistant", content="建议控制饮食..."),
        ]
        ltm.save_conversation("s001", messages)
        loaded_msgs = ltm.get_conversation("s001")

        conv_ok = len(loaded_msgs) == 2
        print(f"  3c 对话原文: {'PASS' if conv_ok else 'FAIL'}")

        # 3d. 会话总结
        summary = SessionSummary(
            user_id="u001", session_id="s001",
            summary_text="用户咨询肌酐偏高问题，建议控制饮食并复查肾功能。",
            model_used="test",
        )
        ltm.save_summary(summary)
        summaries = ltm.get_summaries("u001")

        summary_ok = len(summaries) == 1 and "肌酐" in summaries[0].summary_text
        print(f"  3d 会话总结: {'PASS' if summary_ok else 'FAIL'}")

        all_ok = profile_ok and event_ok and conv_ok and summary_ok
        print(f"  LTM 综合: {'PASS' if all_ok else 'FAIL'}")
        print()
        return all_ok

    finally:
        db.close()
        try:
            os.unlink(tmp_db)
        except OSError:
            pass  # Windows 文件锁，忽略


# ============================================================
# 测试 4: 会话生命周期（STM → LTM 转移）
# ============================================================

def test_lifecycle():
    """验证 SessionLifecycle 能将会话数据从 STM 转移到 LTM"""
    from harness.memory.stm import STMManager
    from harness.memory.lifecycle import SessionLifecycle

    print("=" * 60)
    print("  测试 4: 会话生命周期 (STM → LTM)")
    print("=" * 60)

    ltm, db, tmp_db = _create_test_ltm()

    try:
        lifecycle = SessionLifecycle(ltm_manager=ltm, llm_caller=None, redis_client=None)

        stm = lifecycle.start_session(user_id="u003")
        print(f"  会话 ID: {stm.session_id}")

        stm.add_message("user", "我血糖偏高，需要注意什么？")
        stm.add_message("assistant", "血糖偏高建议控制碳水摄入...")
        stm.add_message("user", "好的，谢谢医生")
        stm.add_message("assistant", "不客气，建议定期复查...")

        lifecycle.end_session(stm)

        stm_msgs_after = len(stm.get_all_messages())
        conv = ltm.get_conversation(stm.session_id)

        print(f"  结束后 STM 消息数: {stm_msgs_after} (期望: 0)")
        print(f"  LTM 保存的对话: {len(conv)} 条")

        lifecycle_ok = stm_msgs_after == 0 and len(conv) == 4
        print(f"  结果: {'PASS' if lifecycle_ok else 'FAIL'}")
        print()
        return lifecycle_ok

    finally:
        db.close()
        try:
            os.unlink(tmp_db)
        except OSError:
            pass  # Windows 文件锁，忽略


# ============================================================
# 测试 5: Agent 集成
# ============================================================

def test_agent_integration():
    """验证 Agent 能通过 state.stm 正常读写记忆"""
    from harness.state.agent_state import AgentState, UserProfile, HumanMessage, AssistantMessage
    from harness.memory.stm import STMManager

    print("=" * 60)
    print("  测试 5: Agent 集成 (state.stm)")
    print("=" * 60)

    stm = STMManager(session_id="agent_test", user_id="u004", redis_client=None)
    state = AgentState(user=UserProfile(user_id="u004", name="李四", age=30))
    state.stm = stm

    state.add_message(HumanMessage(content="血红蛋白偏低是什么原因？"))
    state.add_message(AssistantMessage(content="血红蛋白偏低可能由多种原因引起..."))
    state.add_message(HumanMessage(content="需要做什么检查？"))
    state.add_message(AssistantMessage(content="建议做血常规、铁代谢等检查..."))

    turn_count = state.turn_count
    messages = state.get_messages()
    last_user = state.get_last_human_message()

    print(f"  轮次数: {turn_count} (期望: 2)")
    print(f"  get_messages: {len(messages)} 条")

    ok = turn_count == 2 and len(messages) == 4 and last_user is not None
    print(f"  结果: {'PASS' if ok else 'FAIL'}")
    print()
    return ok


# ============================================================
# 测试 6: Prompt 组装
# ============================================================

def test_prompt_assembly():
    """验证 prompt_context 能正确从 state.stm 获取记忆并组装"""
    from harness.state.agent_state import AgentState, UserProfile, HumanMessage, AssistantMessage
    from harness.memory.stm import STMManager
    from harness.prompt.prompt_context import assemble_final_prompt

    print("=" * 60)
    print("  测试 6: Prompt 组装（记忆注入）")
    print("=" * 60)

    stm = STMManager(session_id="prompt_test", user_id="u005", redis_client=None)
    state = AgentState(user=UserProfile(user_id="u005", name="王五", age=50))
    state.stm = stm
    state.system_prompt = "你是一个专业的医疗检验助手。"

    state.add_message(HumanMessage(content="肌酐120偏高吗？"))
    state.add_message(AssistantMessage(content="肌酐120 μmol/L 略高于正常范围..."))
    state.add_message(HumanMessage(content="饮食需要注意什么？"))
    state.add_message(AssistantMessage(content="建议低蛋白饮食..."))

    prompt = assemble_final_prompt(state, prompt_max_tokens=4000)

    has_system = "医疗检验助手" in prompt
    has_user = "肌酐120偏高吗" in prompt
    has_assistant = "略高于正常范围" in prompt

    print(f"  包含系统提示: {'PASS' if has_system else 'FAIL'}")
    print(f"  包含用户消息: {'PASS' if has_user else 'FAIL'}")
    print(f"  包含助手回复: {'PASS' if has_assistant else 'FAIL'}")

    ok = has_system and has_user and has_assistant
    print(f"  结果: {'PASS' if ok else 'FAIL'}")
    print()
    return ok


# ============================================================
# 主入口
# ============================================================

def main():
    print()
    print("=" * 60)
    print("  记忆系统完整性验证")
    print("=" * 60)
    print()

    results = {}
    results["STM 基本读写"] = test_stm_basic()
    results["STM 自动压缩"] = test_stm_compression()
    results["LTM 读写 (DB)"] = test_ltm()
    results["会话生命周期"] = test_lifecycle()
    results["Agent 集成"] = test_agent_integration()
    results["Prompt 组装"] = test_prompt_assembly()

    print("=" * 60)
    print("  验证汇总")
    print("=" * 60)
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    all_pass = all(results.values())
    print()
    print(f"  总结果: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
