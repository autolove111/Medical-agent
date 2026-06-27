"""快速测试 memory_judge 打分 + 画像提取"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness.llm_adapter.create_agent import LabAgent

# 创建 agent（不需要完整初始化，只用 memory_judge）
agent = LabAgent(
    user_id="test_user",
    session_id="test_session",
    def_prompt="你是一个医疗助手",
    format_prompt="",
)

# 测试用例
test_cases = [
    "我的肌酐值是115，参考范围是60-115，是不是偏高了",
    "我爸有高血压，我妈有糖尿病",
    "好的，谢谢医生",
    "每天熬夜到两点，抽烟一包",
    "吃了降压药之后血压稳定在120/80了",
]

for msg in test_cases:
    result = agent.memory_judge(msg)
    print(f"\n输入: {msg}")
    print(f"输出: {result}")
