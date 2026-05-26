"""
终端多轮对话测试脚本
~~~~~~~~~~~~~~~~~~~~~
实时交互式对话，测试 Agent 多轮对话能力。

运行方式：
    conda activate medagent
    python -u test/终端多轮对话测试.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

from harness.llm_adapter.create_agent import create_agent


def main():
    print("=" * 50)
    print("  医疗检验助手 - 终端多轮对话测试")
    print("=" * 50)

    agent = create_agent(
        user_id="u001",
        user_name="张三",
        user_age=45,
        user_gender="男",
    )

    print("助手已启动，输入 quit 退出\n")

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("再见！")
            break

        reply = agent.chat(user_input)
        print(f"助手: {reply}\n")
        print(f"[轮次: {agent.state.turn_count}]")
        print()


if __name__ == "__main__":
    main()
