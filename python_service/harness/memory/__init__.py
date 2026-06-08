"""
memory模块：统一记忆系统

架构：
- models:     数据模型层（UserProfile, TimelineEvent, ConversationMessage, SessionSummary, StateTracker）
- ltm:        长期记忆层（用户画像、时间轴事件、对话原文、会话总结）
- stm:        短期记忆层（对话轮次缓冲区、状态跟踪器、对话压缩器）
- budget:     Token预算分配器（按优先级填充上下文窗口）
- lifecycle:  会话生命周期管理
- knowledge:  医学知识数据层（参考范围、知识库、数据文件）
"""

from .ltm.ltm_manager import LTMManager
from .stm.stm_manager import STMManager
from .budget.token_budget import TokenBudget
from .lifecycle.session_lifecycle import SessionLifecycle
from .knowledge import REFERENCE_RANGES, get_reference_range, format_reference_text

__all__ = [
    "LTMManager",
    "STMManager",
    "TokenBudget",
    "SessionLifecycle",
    "REFERENCE_RANGES",
    "get_reference_range",
    "format_reference_text",
]
