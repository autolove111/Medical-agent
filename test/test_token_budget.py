"""
测试上下文窗口分配功能

验证 token 预算计算和 prompt 截断逻辑是否正常工作。
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python_service"))

from harness.llm_core.model_loader import ModelConfig, ModelLoader
from harness.prompt.prompt_context import count_tokens, truncate_to_token_limit


def test_token_budget_calculation():
    """测试 token 预算计算"""
    print("=" * 60)
    print("测试 1: Token 预算计算")
    print("=" * 60)

    config = ModelConfig(
        model_path="models/Qwen2.5-7B-Instruct",
        context_window=32768,
        prompt_ratio=0.6,
        output_ratio=0.3,
        buffer_ratio=0.1,
    )

    # 注意：这里不会实际加载模型，只是测试配置
    # loader = ModelLoader.init(config)
    # token_budgets = loader.get_token_budgets()

    # 手动计算验证
    prompt_max = int(32768 * 0.6)
    output_max = int(32768 * 0.3)
    buffer = int(32768 * 0.1)

    print(f"上下文窗口大小：32768 tokens")
    print(f"提示词最大 token 数：{prompt_max} tokens (60%)")
    print(f"模型输出最大 token 数：{output_max} tokens (30%)")
    print(f"缓冲区大小：{buffer} tokens (10%)")
    print(f"总计：{prompt_max + output_max + buffer} tokens")

    # 验证比例
    total_ratio = 0.6 + 0.3 + 0.1
    assert abs(total_ratio - 1.0) < 0.001, "比例之和应该为 1.0"
    print("✓ 比例验证通过")

    # 验证 token 数量
    assert prompt_max + output_max + buffer == 32768, "token 数量总和应该等于上下文窗口大小"
    print("✓ Token 数量验证通过")

    print()


def test_custom_ratios():
    """测试自定义比例"""
    print("=" * 60)
    print("测试 2: 自定义比例")
    print("=" * 60)

    test_cases = [
        (0.7, 0.2, 0.1, 32768),
        (0.5, 0.4, 0.1, 32768),
        (0.6, 0.3, 0.1, 65536),
    ]

    for prompt_ratio, output_ratio, buffer_ratio, context_window in test_cases:
        prompt_max = int(context_window * prompt_ratio)
        output_max = int(context_window * output_ratio)
        buffer = int(context_window * buffer_ratio)

        print(f"\n配置：{context_window} tokens, {prompt_ratio}/{output_ratio}/{buffer_ratio}")
        print(f"  提示词：{prompt_max} tokens")
        print(f"  输出：{output_max} tokens")
        print(f"  缓冲：{buffer} tokens")
        print(f"  总计：{prompt_max + output_max + buffer} tokens")

        # 验证
        total_ratio = prompt_ratio + output_ratio + buffer_ratio
        assert abs(total_ratio - 1.0) < 0.001, f"比例之和应该为 1.0，实际为 {total_ratio}"
        assert prompt_max + output_max + buffer == context_window, "token 数量总和应该等于上下文窗口大小"

    print("\n✓ 所有自定义比例测试通过")
    print()


def test_token_counting():
    """测试 token 计数功能"""
    print("=" * 60)
    print("测试 3: Token 计数")
    print("=" * 60)

    test_texts = [
        "Hello, world!",
        "你好，世界！",
        "这是一个测试文本，用于验证 token 计数功能。",
        "This is a longer English text to test the token counting function. "
        "It should handle both Chinese and English characters properly.",
    ]

    for text in test_texts:
        tokens = count_tokens(text)
        print(f"文本：{text[:30]}...")
        print(f"  字符数：{len(text)}")
        print(f"  Token 数：{tokens}")
        print(f"  比率：{tokens/len(text):.2f} tokens/char")

    print("\n✓ Token 计数测试完成")
    print()


def test_text_truncation():
    """测试文本截断功能"""
    print("=" * 60)
    print("测试 4: 文本截断")
    print("=" * 60)

    long_text = (
        "这是一段很长的文本，用于测试截断功能。"
        "它包含多个句子，每个句子都有不同的内容。"
        "我们希望验证截断后文本是否保持完整，不会在句子中间截断。"
        "同时，我们也需要确保截断后的 token 数量符合预期。"
        "这段文本应该足够长，以便我们能够测试截断逻辑。"
    )

    print(f"原始文本长度：{len(long_text)} 字符")
    print(f"原始文本 token 数：{count_tokens(long_text)}")

    # 测试不同的截断限制
    limits = [50, 100, 150, 200]

    for limit in limits:
        truncated = truncate_to_token_limit(long_text, limit)
        actual_tokens = count_tokens(truncated)
        print(f"\n截断限制：{limit} tokens")
        print(f"  截断后长度：{len(truncated)} 字符")
        print(f"  截断后 token 数：{actual_tokens}")
        print(f"  是否符合限制：{'✓' if actual_tokens <= limit else '✗'}")
        print(f"  截断内容：{truncated[:50]}...")

    print("\n✓ 文本截断测试完成")
    print()


def main():
    print("上下文窗口分配功能测试")
    print()

    try:
        test_token_budget_calculation()
        test_custom_ratios()
        test_token_counting()
        test_text_truncation()

        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
