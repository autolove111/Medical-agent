"""
模型加载 & Agent 创建测试脚本
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
逐级测试 harness 层各组件，确认本地模型能正常加载和推理。

运行方式：
    cd e:/xiangmu/dachuang/langchain_service
    python -m test.create_modle_test
"""

import sys
import os
import logging

# 将 langchain_service 加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "langchain_service"))

# 配置日志，方便观察加载过程
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("test")


def test_model_loader():
    """测试 1：模型加载器能否正常初始化和加载模型"""
    print("\n" + "=" * 50)
    print("测试 1：ModelLoader 模型加载")
    print("=" * 50)

    from harness.llm_core.model_loader import ModelLoader, ModelConfig

    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "Qwen2.5-7B-Instruct")
    config = ModelConfig(
        model_path=model_path,
        use_4bit=True,
        temperature=0.7,
        max_new_tokens=512,
    )

    print(f"模型路径: {model_path}")
    print("正在加载模型（首次加载需要较长时间）...")

    loader = ModelLoader.init(config)
    loader.load()  # 显式触发加载

    print(f"Tokenizer 类型: {type(loader.tokenizer).__name__}")
    print(f"Model 类型:     {type(loader.model).__name__}")
    print("[PASS] 模型加载成功\n")
    return loader


def test_chat_model(loader):
    """测试 2：ChatModel 能否正常调用模型生成回复"""
    print("=" * 50)
    print("测试 2：ChatModel 同步调用 (invoke)")
    print("=" * 50)

    from harness.llm_adapter.chat_model import ChatModel, Message

    chat = ChatModel(loader)
    messages = [
        Message(role="system", content="你是一个医疗助手"),
        Message(role="user", content="血红蛋白偏低是什么意思？请用一句话回答"),
    ]

    print("输入: 血红蛋白偏低是什么意思？")
    print("生成中...")

    reply = chat.invoke(messages)

    print(f"回复: {reply}")
    assert isinstance(reply, str) and len(reply) > 0, "回复不能为空"
    print("[PASS] 同步调用成功\n")
    return chat


def test_chat_stream(chat):
    """测试 3：ChatModel 流式调用能否正常输出"""
    print("=" * 50)
    print("测试 3：ChatModel 流式调用 (stream)")
    print("=" * 50)

    from harness.llm_adapter.chat_model import Message

    messages = [
        Message(role="user", content="白细胞偏高常见原因有哪些？请简要列举"),
    ]

    print("输入: 白细胞偏高常见原因有哪些？")
    print("流式回复: ", end="", flush=True)

    full_reply = ""
    for chunk in chat.stream(messages):
        print(chunk.content, end="", flush=True)
        full_reply += chunk.content

    print()
    assert len(full_reply) > 0, "流式回复不能为空"
    print("[PASS] 流式调用成功\n")


def test_create_agent():
    """测试 4：create_agent 工厂函数能否一步创建 Agent"""
    print("=" * 50)
    print("测试 4：create_agent 工厂函数")
    print("=" * 50)

    from harness.llm_adapter.create_agent import create_agent

    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "Qwen2.5-7B-Instruct")

    print("创建 Agent...")
    agent = create_agent(model_path=model_path, use_4bit=True, temperature=0.7)
    print("Agent 创建成功")

    # 测试多轮对话
    print("\n--- 第 1 轮 ---")
    print("用户: 你好，请自我介绍")
    reply1 = agent.chat("你好，请自我介绍")
    print(f"Agent: {reply1}")

    print("\n--- 第 2 轮 ---")
    print("用户: 血红蛋白偏低怎么办？")
    reply2 = agent.chat("血红蛋白偏低怎么办？")
    print(f"Agent: {reply2}")

    assert len(agent.history) == 5, f"对话历史应有 5 条（system+2轮），实际 {len(agent.history)}"
    print(f"\n对话历史条数: {len(agent.history)}")
    print("[PASS] Agent 多轮对话成功\n")


def main():
    print("=" * 50)
    print("  harness 层组件测试")
    print("=" * 50)

    # 测试 1：模型加载
    loader = test_model_loader()

    # 测试 2：同步调用
    chat = test_chat_model(loader)

    # 测试 3：流式调用
    test_chat_stream(chat)

    # 测试 4：Agent 创建 + 多轮对话
    test_create_agent()

    print("=" * 50)
    print("  全部测试通过!")
    print("=" * 50)


if __name__ == "__main__":
    main()
