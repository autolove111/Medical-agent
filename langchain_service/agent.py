import logging
import asyncio
from typing import List, Dict, Optional
from langchain.callbacks.base import BaseCallbackHandler
from langchain.agents import initialize_agent, AgentType
# 核心修复：更换 Memory 组件，避免 Token 计算导致的崩溃
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tools import tools, set_current_user_id  # 【修复】导入 set_current_user_id
from rag import retrieve_medical_knowledge
from config import settings

logger = logging.getLogger(__name__)

# LLM 实例 - 延迟初始化，便于诊断
llm = None

def get_llm():
    """延迟初始化 LLM，避免启动时失败"""
    global llm
    if llm is None:
        try:
            logger.info("正在初始化 LLM (DashScope)...")
            llm = ChatOpenAI(
                model=settings.DASHSCOPE_MODEL,
                openai_api_key=settings.DASHSCOPE_API_KEY,
                openai_api_base=settings.DASHSCOPE_BASE_URL,
                temperature=settings.TEMPERATURE,
                max_tokens=settings.MAX_TOKENS,
                streaming=False
            )
            logger.info("LLM 初始化成功")
        except Exception as e:
            logger.error(f"LLM 初始化失败: {e}")
            raise
    return llm

# 系统提示词
SYSTEM_PROMPT = """你是一个专业的医学实验室AI智能体，名为 MedLabAgent。
你具备深厚的医学检验知识，能分析报告指标并提供专业的建议。

【重要】请遵循以下规则：
1. 任何诊断建议后必须提示：'以上建议仅供参考，请以临床医生诊断为准'
2. 利用医学知识库工具查询权威信息
3. 考虑用户的既往史和过敏信息
4. 分析时必须引用知识库来源
5. 回答最后输出元数据标记：[META|医疗:是或否|疾病:疾病名称或无|过敏:药物名称或无]

【用户上下文处理】（重要！！！）
- 当需要查询用户的医学历史时，你将收到一个 UUID 格式的 user_id
- 你必须使用这个 user_id 来查询用户的病历
- 不要试图自行猜测或使用中文描述来替代 user_id
- 必须使用 QueryUserHistory 工具，并传入正确的 user_id 格式

【示例标记】
[META|医疗:是|疾病:2型糖尿病|过敏:青霉素]
[META|医疗:否|疾病:无|过敏:无]
"""

class MedicalAgent:
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.agent = self._create_agent()
    
    def _create_agent(self):
        """创建医学 Agent"""
        try:
            # 核心修复：使用窗口记忆，记住最近 5 轮对话，不再计算 Token
            memory = ConversationBufferWindowMemory(
                k=5, 
                memory_key="chat_history",
                return_messages=True
            )
            
            # 初始化 Agent
            agent = initialize_agent(
                tools=tools,
                llm=get_llm(),
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                memory=memory,
                verbose=True,
                max_iterations=5,
                early_stopping_method="generate"
            )
            
            logger.info(f"创建医学 Agent 成功 (用户ID: {self.user_id})")
            return agent
        except Exception as e:
            logger.error(f"创建 Agent 失败: {e}", exc_info=True)
            return None
    
    def process_query(
        self,
        query: str,
        user_context: Optional[str] = None
    ) -> tuple[str, list]:
        """
        处理用户查询
        """
        if not self.agent:
            return "【Agent 初始化失败】无法处理查询", []
        
        try:
            # 【修复】设置全局 user_id 上下文，让工具函数可以访问
            set_current_user_id(self.user_id)
            
            # 1. RAG 检索相关知识
            rag_result, sources = retrieve_medical_knowledge(query)
            
            # 2. 组织完整提示词
            # 【关键修复】将 user_id 明确注入到提示词中
            user_id_info = f"【当前用户ID】{self.user_id}" if self.user_id else "【当前用户ID】未登录（匿名模式）"
            
            full_prompt = f"""{SYSTEM_PROMPT}

{user_id_info}

【当前知识库检索结果】
{rag_result}

【用户医学档案】
{user_context or '无用户档案'}

【用户问题】
{query}

请基于上述信息和可用工具，给出专业的分析和建议。
"""
            
            # 3. 调用 Agent（同时记录中间思路/工具调用）
            class TraceCallbackHandler(BaseCallbackHandler):
                def __init__(self):
                    self.events = []

                def on_agent_action(self, action, **kwargs):
                    try:
                        self.events.append({
                            "type": "agent_action",
                            "tool": getattr(action, "tool", None),
                            "tool_input": getattr(action, "tool_input", None),
                            "log": getattr(action, "log", None)
                        })
                    except Exception as e:
                        self.events.append({"type": "agent_action_error", "error": str(e)})

                def on_tool_end(self, output, **kwargs):
                    self.events.append({"type": "tool_end", "output": output})

                def on_agent_finish(self, finish, **kwargs):
                    try:
                        result = getattr(finish, "return_values", finish)
                    except Exception:
                        result = str(finish)
                    self.events.append({"type": "agent_finish", "result": result})

            tracer = TraceCallbackHandler()
            # 使用 Agent 推理
            response = self.agent.run(full_prompt, callbacks=[tracer])
            self.last_trace = tracer.events
            
            logger.info(f"查询处理成功: {query[:50]}")
            return response, sources
        
        except Exception as e:
            logger.error(f"查询处理失败: {e}")
            return f"【处理异常】{str(e)}", []
    
    def stream_query(self, query: str, user_context: Optional[str] = None):
        raise NotImplementedError("stream_query 已被弃用：服务改为非流式 RAG 增强生成")

# 工厂函数
def create_medical_agent(user_id: Optional[str] = None) -> MedicalAgent:
    return MedicalAgent(user_id)