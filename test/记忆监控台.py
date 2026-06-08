"""
记忆系统实时监控台
~~~~~~~~~~~~~~~~~~
查看任意用户的短期记忆（STM）和长期记忆（LTM）实时状态。

用法：
    cd python_service
    python ../test/记忆监控台.py

交互命令：
    stm <user_id>      — 查看某用户的短期记忆（当前会话）
    ltm <user_id>      — 查看某用户的长期记忆（画像+事件+总结）
    all <user_id>      — 同时查看 STM + LTM
    sessions           — 列出所有活跃会话
    watch <user_id>    — 持续监控某用户的 STM（每3秒刷新）
    help               — 显示帮助
    quit               — 退出
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

for m in list(sys.modules):
    if any(p in m for p in ("harness", "memory", "service")):
        del sys.modules[m]

from harness.memory.stm import get_active_stm, list_active_stms


# ============================================================
# 格式化输出
# ============================================================

def fmt_stm(user_id: str) -> str:
    """格式化某用户的短期记忆"""
    stm = get_active_stm(user_id)
    if not stm:
        return f"  用户 '{user_id}' 无活跃 STM 会话"

    lines = []
    lines.append(f"  会话 ID: {stm.session_id}")
    lines.append(f"  用户 ID: {stm.user_id}")

    # 消息统计
    all_msgs = stm.get_all_messages()
    summaries = stm.conversation_buffer.summaries
    buffer = stm.conversation_buffer

    lines.append(f"  ┌─ 对话缓冲区 ─────────────────────────")
    lines.append(f"  │ 消息数: {len(buffer.messages)} 条")
    lines.append(f"  │ 摘要数: {len(summaries)} 条")
    lines.append(f"  │ Token: {buffer.total_tokens} / {buffer.max_tokens}")
    usage_pct = (buffer.total_tokens / buffer.max_tokens * 100) if buffer.max_tokens > 0 else 0
    bar_len = 30
    filled = int(bar_len * usage_pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    lines.append(f"  │ [{bar}] {usage_pct:.0f}%")
    lines.append(f"  └────────────────────────────────────")

    # 摘要
    if summaries:
        lines.append(f"  ┌─ 历史摘要 ─────────────────────────")
        for i, s in enumerate(summaries, 1):
            content = s.get("content", "")[:80]
            lines.append(f"  │ {i}. {content}")
        lines.append(f"  └────────────────────────────────────")

    # 最近消息
    recent = stm.get_recent_messages(n=5)
    if recent:
        lines.append(f"  ┌─ 最近对话（{len(recent)} 条）────────────────")
        for msg in recent:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            # 截断长消息
            if len(content) > 60:
                content = content[:60] + "..."
            icon = "👤" if role == "user" else "🤖" if role == "assistant" else "📋"
            lines.append(f"  │ {icon} [{role}] {content}")
        lines.append(f"  └────────────────────────────────────")

    return "\n".join(lines)


def fmt_ltm(user_id: str) -> str:
    """格式化某用户的长期记忆"""
    from harness.memory.ltm import LTMManager

    tmp_path = os.path.join(os.path.dirname(__file__), "..", "python_service", "data", "ltm")
    ltm = LTMManager(base_path=tmp_path)

    lines = []

    # 用户画像
    profile = ltm.get_user_profile(user_id)
    lines.append(f"  ┌─ 用户画像 ─────────────────────────")
    if profile:
        lines.append(f"  │ 姓名: {profile.name or '未设置'}")
        lines.append(f"  │ 年龄: {profile.age or '未设置'}")
        lines.append(f"  │ 性别: {profile.gender or '未设置'}")
        if profile.chronic_diseases:
            lines.append(f"  │ 慢性病: {', '.join(profile.chronic_diseases)}")
        if profile.allergies:
            lines.append(f"  │ 过敏史: {', '.join(profile.allergies)}")
        if profile.medications:
            lines.append(f"  │ 用药: {', '.join(profile.medications)}")
    else:
        lines.append(f"  │ （无数据）")
    lines.append(f"  └────────────────────────────────────")

    # 会话总结
    summaries = ltm.get_summaries(user_id, limit=5)
    lines.append(f"  ┌─ 会话总结（最近 {len(summaries)} 条）──────────")
    if summaries:
        for i, s in enumerate(summaries, 1):
            text = s.summary_text[:80] if s.summary_text else ""
            lines.append(f"  │ {i}. [{s.session_id[:20]}...] {text}")
    else:
        lines.append(f"  │ （无数据）")
    lines.append(f"  └────────────────────────────────────")

    # 时间轴事件
    events = ltm.get_events(user_id, limit=5)
    lines.append(f"  ┌─ 时间轴事件（最近 {len(events)} 条）────────")
    if events:
        for i, e in enumerate(events, 1):
            content = e.content[:60] if e.content else ""
            lines.append(f"  │ {i}. [{e.event_type}] {content}")
    else:
        lines.append(f"  │ （无数据）")
    lines.append(f"  └────────────────────────────────────")

    return "\n".join(lines)


# ============================================================
# 交互式命令行
# ============================================================

def cmd_help():
    print("""
  命令列表：
    stm <user_id>      查看短期记忆（当前会话）
    ltm <user_id>      查看长期记忆（画像+事件+总结）
    all <user_id>      同时查看 STM + LTM
    sessions           列出所有活跃会话
    watch <user_id>    持续监控 STM（每3秒刷新，Ctrl+C 停止）
    help               显示本帮助
    quit               退出
""")


def cmd_sessions():
    active = list_active_stms()
    if not active:
        print("  当前无活跃会话")
        return
    print(f"  活跃会话 ({len(active)} 个):")
    for uid, stm in active.items():
        msg_count = len(stm.get_all_messages())
        tokens = stm.conversation_buffer.total_tokens
        print(f"    - {uid}: {msg_count} 条消息, {tokens} tokens")


def main():
    print()
    print("=" * 60)
    print("  记忆系统实时监控台")
    print("=" * 60)
    print()
    print("  提示: 先通过 API 调用产生对话，再用以下命令查看。")
    print("  或直接输入 'stm <user_id>' 测试（需先创建 Agent）。")
    print()
    cmd_help()

    while True:
        try:
            raw = input("monitor> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见！")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "quit" or cmd == "exit":
            print("  再见！")
            break

        elif cmd == "help":
            cmd_help()

        elif cmd == "sessions":
            cmd_sessions()

        elif cmd == "stm":
            if not arg:
                print("  用法: stm <user_id>")
                continue
            print()
            print(fmt_stm(arg))
            print()

        elif cmd == "ltm":
            if not arg:
                print("  用法: ltm <user_id>")
                continue
            print()
            print(fmt_ltm(arg))
            print()

        elif cmd == "all":
            if not arg:
                print("  用法: all <user_id>")
                continue
            print()
            print(f"  ╔══ 短期记忆 (STM) ════════════════════╗")
            print(fmt_stm(arg))
            print(f"  ╚══════════════════════════════════════╝")
            print()
            print(f"  ╔══ 长期记忆 (LTM) ════════════════════╗")
            print(fmt_ltm(arg))
            print(f"  ╚══════════════════════════════════════╝")
            print()

        elif cmd == "watch":
            if not arg:
                print("  用法: watch <user_id>")
                continue
            print(f"  持续监控 '{arg}' 的 STM（Ctrl+C 停止）...")
            try:
                while True:
                    os.system("cls" if os.name == "nt" else "clear")
                    print(f"  [{time.strftime('%H:%M:%S')}] STM 实时监控 — 用户: {arg}")
                    print()
                    print(fmt_stm(arg))
                    print()
                    print("  按 Ctrl+C 停止监控")
                    time.sleep(3)
            except KeyboardInterrupt:
                print("\n  监控已停止")

        else:
            print(f"  未知命令: {cmd}，输入 help 查看帮助")


if __name__ == "__main__":
    main()
