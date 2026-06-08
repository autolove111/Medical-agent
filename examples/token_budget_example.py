"""
上下文窗口分配示例

演示如何使用 token 预算功能来管理模型的上下文窗口分配。

当前模型：Qwen2.5-7B-Instruct
上下文窗口：32768 tokens

分配策略：
- 60% 提示词：19660 tokens
- 30% 模型输出：9830 tokens
- 10% 缓冲：3276 tokens
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

from harness.llm_adapter.create_agent import create_agent
from harness.llm_core.model_loader import ModelLoader


def main():
    print("=" * 60)
    print("上下文窗口分配示例")
    print("=" * 60)

    # 示例 1：使用默认配置
    print("\n1. 使用默认配置（32768 tokens，60/30/10 分配）")
    print("-" * 40)

    agent = create_agent(
        user_id="demo_user",
        user_name="张三",
        user_age=45,
        user_gender="男",
    )

    # 获取 token 预算
    token_budgets = agent.chat_model.loader.get_token_budgets()
    print(f"上下文窗口大小：{token_budgets['context_window']} tokens")
    print(f"提示词最大 token 数：{token_budgets['prompt_max_tokens']} tokens")
    print(f"模型输出最大 token 数：{token_budgets['output_max_tokens']} tokens")
    print(f"缓冲区大小：{token_budgets['buffer_tokens']} tokens")

    # 示例 2：自定义分配比例
    print("\n2. 自定义分配比例（70/20/10）")
    print("-" * 40)

    agent2 = create_agent(
        user_id="demo_user2",
        user_name="李四",
        user_age=30,
        user_gender="女",
        prompt_ratio=0.7,
        output_ratio=0.2,
        buffer_ratio=0.1,
    )

    token_budgets2 = agent2.chat_model.loader.get_token_budgets()
    print(f"上下文窗口大小：{token_budgets2['context_window']} tokens")
    print(f"提示词最大 token 数：{token_budgets2['prompt_max_tokens']} tokens")
    print(f"模型输出最大 token 数：{token_budgets2['output_max_tokens']} tokens")
    print(f"缓冲区大小：{token_budgets2['buffer_tokens']} tokens")

    # 示例 3：使用更大的上下文窗口（如果模型支持）
    print("\n3. 使用更大的上下文窗口（65536 tokens）")
    print("-" * 40)

    agent3 = create_agent(
        user_id="demo_user3",
        user_name="王五",
        user_age=25,
        user_gender="男",
        context_window=65536,
        prompt_ratio=0.6,
        output_ratio=0.3,
        buffer_ratio=0.1,
    )

    token_budgets3 = agent3.chat_model.loader.get_token_budgets()
    print(f"上下文窗口大小：{token_budgets3['context_window']} tokens")
    print(f"提示词最大 token 数：{token_budgets3['prompt_max_tokens']} tokens")
    print(f"模型输出最大 token 数：{token_budgets3['output_max_tokens']} tokens")
    print(f"缓冲区大小：{token_budgets3['buffer_tokens']} tokens")

    # 示例 4：测试对话
    print("\n4. 测试对话（演示 token 预算控制）")
    print("-" * 40)

    reply = agent.chat("血红蛋白偏低是什么意思？")
    print(f"用户：血红蛋白偏低是什么意思？")
    print(f"助手：{reply[:100]}...")  # 只显示前100个字符

    print("\n" + "=" * 60)
    print("示例完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
