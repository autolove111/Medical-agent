"""
双图架构的 FastAPI 集成模块

暴露两个关键端点：
  1. /api/v1/graph-inference - 完整的双图推理管道
  2. /api/v1/graph-debug - 调试端点，输出中间结果
"""

import logging
from typing import Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine
import os

from .indicator_graph.graph_utils import GraphLoader

try:
    from graph.indicator_graph.indicator_gat import IndicatorGAT
except ImportError as e:
    logging.warning(f"IndicatorGAT not found: {e}")
    IndicatorGAT = None

try:
    from graph.department_agent_graph.expert_gat import ExpertGAT
except ImportError as e:
    logging.warning(f"ExpertGAT not found: {e}")
    ExpertGAT = None

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/v1", tags=["graph-inference"])

# 全局 GAT 模块实例（延迟初始化）
_graph_loader = None
_indicator_gat = None
_expert_gat = None


# ============================================
# 图模型初始化
# 作用：在应用启动时从数据库加载图结构，创建 IndicatorGAT 和 ExpertGAT 对象
# 执行步骤：创建数据库引擎 → GraphLoader → 指标图 → ExpertGAT 映射 → 专家图
# 特性：延迟初始化，容错机制（某个 GAT 失败不影响整体）
# 返回值：True 成功，False 失败
# ============================================
def init_graph_models():
    """初始化图模型（在应用启动时调用）"""
    global _graph_loader, _indicator_gat, _expert_gat
    
    try:
        from core.config import settings
        
        # 创建数据库连接
        db_url = settings.SQLALCHEMY_DATABASE_URL
        engine = create_engine(db_url, pool_pre_ping=True)
        
        # 初始化图加载器
        _graph_loader = GraphLoader(engine)
        logger.info("✅ GraphLoader initialized")
        
        # 加载指标图
        if IndicatorGAT is not None:
            indicator_graph = _graph_loader.load_indicator_graph()
            _indicator_gat = IndicatorGAT(indicator_graph)
            logger.info("✅ IndicatorGAT initialized")
        else:
            logger.warning("⚠️ IndicatorGAT not available, skipping...")
        
        # 加载映射和专家图
        if ExpertGAT is not None:
            indicator_dept_mapping = _graph_loader.load_indicator_dept_mapping()
            expert_graph = _graph_loader.load_expert_graph()
            _expert_gat = ExpertGAT(expert_graph, indicator_dept_mapping)
            logger.info("✅ ExpertGAT initialized")
        else:
            logger.warning("⚠️ ExpertGAT not available, skipping...")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize graph models: {e}", exc_info=True)
        # 返回 False 以便调用者判断是否降级
        return False
    
    return True


# ============================================
# 获取或懒加载图模型
# 作用：访问全局的 IndicatorGAT 和 ExpertGAT 对象，如果未初始化则触发初始化
# 机制：单例模式 + 延迟加载（只初始化一次）
# 调用时机：API 请求到达时，从这里获取已加载的推理模型
# 返回值：元组 (indicator_gat, expert_gat)
# 异常处理：如果初始化失败，抛出 RuntimeError
# ============================================
def get_graph_models():
    """获取或懒加载图模型"""
    global _graph_loader, _indicator_gat, _expert_gat
    
    if _indicator_gat is None or _expert_gat is None:
        if not init_graph_models():
            raise RuntimeError("Graph models initialization failed")
    
    return _indicator_gat, _expert_gat


# ============================================
# Pydantic 请求/响应模型
# ============================================

class GraphInferenceRequest(BaseModel):
    """双图推理请求"""
    patient_labs: Dict[str, float]
    indicator_abnormality_threshold: float = 0.1
    top_k_indicators: int = 5
    top_k_agents: int = 3


class IndicatorCluster(BaseModel):
    """指标簇信息"""
    key_indicators: List[str]
    weights: Dict[str, float]
    clusters: List[List[str]]


class ExpertRecommendation(BaseModel):
    """专家推荐信息"""
    recommended_agents: List[str]
    agent_weights: Dict[str, float]
    involved_departments: List[str]
    collaboration_notes: List[str]


class DoubleGraphResult(BaseModel):
    """双图推理完整结果"""
    indicator_cluster: IndicatorCluster
    expert_recommendations: ExpertRecommendation
    prompt_injection: str
    is_complex: bool
    complexity_score: float


class GraphDebugResult(BaseModel):
    """调试结果（包含中间步骤）"""
    indicator_cluster: Dict
    expert_recommendations: Dict
    prompt_injection: str


# ============================================
# API 端点
# ============================================

# ============================================
# 双图推理完整管道（核心 API 端点）
# 作用：整合 IndicatorGAT + ExpertGAT 的完整推理流程
# 输入：患者化验值 (patient_labs = {指标名: 数值})
# 核心步骤：
#   Step 1: IndicatorGAT 分析化验值 → 计算异常分数 + 图消息传递 + 识别关键指标簇
#   Step 2: 降级处理 → 如果没识别出簇，用粗粒度的"异常分数>阈值"方法
#   Step 3: ExpertGAT 推理 → 根据关键指标推荐诊疗路径和 Agent
#   Step 4: 生成 Prompt Injection → 将图谱结果格式化为 LLM 可用的约束文本
#   Step 5: 计算复杂度评分 → 用于后续多轮对话决策
# 输出：DoubleGraphResult (包含指标簇 + 专家推荐 + Prompt 约束 + 复杂度评分)
# 日志：每个步骤都有 emoji 标记便于追踪执行流程
# ============================================
@router.post("/graph-inference")
async def run_double_graph_inference(request: GraphInferenceRequest) -> DoubleGraphResult:
    """
    执行完整的双图推理管道
    
    流程：
      1. IndicatorGAT 分析化验值，识别关键指标簇
      2. ExpertGAT 基于指标簇，推荐调用的 Agent 及优先级
      3. 生成 Prompt 注入文本用于后续 LLM 推理
    
    Args:
        request: 包含患者化验值的请求
    
    Returns:
        推理结果，包含指标簇、专家推荐和生成的约束提示词
    """
    try:
        logger.info(f"🔍 Running double graph inference with {len(request.patient_labs)} labs")
        
        indicator_gat, expert_gat = get_graph_models()
        
        # 步骤 1：指标 GAT 推理
        logger.info("📊 Step 1: Running IndicatorGAT...")
        indicator_result = indicator_gat.forward(request.patient_labs)
        
        key_indicators = indicator_result.get('key_indicators', [])
        if not key_indicators:
            logger.warning("⚠️ No key indicators found, using all abnormal indicators")
            abnormality_scores = indicator_result.get('abnormality_scores', {})
            key_indicators = [
                ind for ind, score in abnormality_scores.items()
                if score >= request.indicator_abnormality_threshold
            ][:request.top_k_indicators]
        
        # 步骤 2：专家 GAT 推理
        logger.info("👨‍⚕️ Step 2: Running ExpertGAT...")
        indicator_weights = indicator_result.get('weights', {})
        expert_result = expert_gat.forward(key_indicators, indicator_weights)
        
        recommended_agents = expert_result.get('recommended_agents', [])
        agent_weights = expert_result.get('agent_weights', {})
        
        # 步骤 3：生成 Prompt 注入文本
        logger.info("💬 Step 3: Generating prompt injection...")
        prompt_injection = _generate_prompt_injection(
            key_indicators,
            indicator_result,
            recommended_agents,
            expert_result
        )
        
        # 步骤 4：计算复杂度评分
        is_complex = len(recommended_agents) > 1 or len(key_indicators) > 2
        complexity_score = min(len(recommended_agents) / 3.0, 1.0) + \
                          min(len(key_indicators) / 5.0, 1.0)
        complexity_score = min(complexity_score / 2.0, 1.0)
        
        # 构建响应
        response = DoubleGraphResult(
            indicator_cluster=IndicatorCluster(
                key_indicators=key_indicators,
                weights=indicator_weights,
                clusters=indicator_result.get('clusters', [])
            ),
            expert_recommendations=ExpertRecommendation(
                recommended_agents=recommended_agents,
                agent_weights=agent_weights,
                involved_departments=expert_result.get('involved_departments', []),
                collaboration_notes=expert_result.get('collaboration_notes', [])
            ),
            prompt_injection=prompt_injection,
            is_complex=is_complex,
            complexity_score=complexity_score,
        )
        
        logger.info(
            f"✅ Graph inference completed: "
            f"is_complex={is_complex}, "
            f"complexity_score={complexity_score:.2f}, "
            f"agents={recommended_agents}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Graph inference failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 双图推理调试端点（开发/问题诊断用）
# 作用：返回推理过程中的所有中间结果原始值，用于调试和问题诊断
# 区别于 run_double_graph_inference：不进行后处理、不计算复杂度、直接返回原始结果
# 输入：同上（patient_labs）
# 输出原始结果：
#   indicator_result：IndicatorGAT 完整输出（包含 abnormality_scores、weights、clusters）
#   expert_result：ExpertGAT 完整输出（所有中间计算值）
#   prompt_injection：Prompt 约束文本
# 用途：开发者验证图结构是否正确、检查中间计算是否符合预期
# ============================================
@router.post("/graph-debug")
async def debug_graph_inference(request: GraphInferenceRequest) -> GraphDebugResult:
    """
    调试端点：返回双图推理的所有中间结果
    
    用于调试和验证图结构与推理过程
    """
    try:
        logger.info("🔧 Running graph inference in debug mode...")
        
        indicator_gat, expert_gat = get_graph_models()
        
        # 指标 GAT
        indicator_result = indicator_gat.forward(request.patient_labs)
        key_indicators = indicator_result.get('key_indicators', [])
        
        # 专家 GAT
        expert_result = expert_gat.forward(
            key_indicators,
            indicator_result.get('weights', {})
        )
        
        # 生成 Prompt
        prompt_injection = _generate_prompt_injection(
            key_indicators,
            indicator_result,
            expert_result.get('recommended_agents', []),
            expert_result
        )
        
        return GraphDebugResult(
            indicator_cluster=indicator_result,
            expert_recommendations=expert_result,
            prompt_injection=prompt_injection,
        )
        
    except Exception as e:
        logger.error(f"❌ Graph debug failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# 辅助函数
# ============================================

# ============================================
# 生成 Prompt Injection 约束文本
# 作用：将图推理的复杂计算结果转化为自然语言，注入到 LLM 系统提示词中
# 工作原理：
#   1. 从 indicator_result 中提取权重最高的指标（Top 5）
#   2. 格式化为 "关键指标簇：wbc(0.95), rbc(0.92), ..." 
#   3. 从 expert_result 中提取推荐的诊疗路径 "Agent1 → Agent2 → Agent3"
#   4. 添加协作备注说明不同科室需要关注的事项
# 约束文本示例：
#   [系统约束 - 基于医学图谱分析]
#   关键指标簇：wbc(0.95), rbc(0.92), ne(0.88), ...
#   建议诊疗路径：Hematology → Nephrology → Endocrinology
#     • 关注红细胞形态
#     • 评估肾脏功能
#   [end system constraints]
# 注入机制：这段文本会被添加到 LLM 的 messages 中，强制 LLM 遵循医学图谱的逻辑
# ============================================
def _generate_prompt_injection(
    key_indicators: List[str],
    indicator_result: Dict,
    recommended_agents: List[str],
    expert_result: Dict
) -> str:
    """
    生成用于注入到 LLM Prompt 的约束文本
    
    这段文本会被添加到系统提示数中，强制 LLM 遵循图谱建议的诊疗逻辑。
    """
    lines = []
    lines.append("[系统约束 - 基于医学图谱分析]")
    
    # 添加指标层约束
    if key_indicators:
        indicator_weights = indicator_result.get('weights', {})
        sorted_indicators = sorted(
            indicator_weights.items() if indicator_weights else [],
            key=lambda x: x[1],
            reverse=True
        )
        
        weight_text = ", ".join([
            f"{ind}({weight:.2f})"
            for ind, weight in sorted_indicators[:5]
        ])
        lines.append(f"关键指标簇：{weight_text}")
        lines.append(f"请特别关注这些指标之间的生理耦合关系，结合患者的完整临床表现进行多维度评估。")
    
    # 添加专家层约束
    collaboration_notes = expert_result.get('collaboration_notes', [])
    if recommended_agents:
        agents_text = " → ".join(recommended_agents[:3])
        lines.append(f"建议诊疗路径：{agents_text}")
        
        if collaboration_notes:
            for note in collaboration_notes[:2]:
                lines.append(f"  • {note}")
    
    lines.append("[end system constraints]")
    
    return "\n".join(lines)


# ============================================
# 应用启动钩子
# ============================================

# ============================================
# 应用启动钩子和路由注册
# 作用：将图推理路由注册到 FastAPI 应用，并在启动时初始化所有 GAT 模型
# 执行流程：
#   1. include_router(router) → 将 /api/v1/graph-inference 和 /api/v1/graph-debug 加入应用
#   2. @app.on_event("startup") → 应用启动时执行 init_graph_models()
# 调用时机：在 FastAPI 应用初始化阶段调用此函数
# 使用示例：
#   from graph.graph_inference import register_graph_routes
#   app = FastAPI()
#   register_graph_routes(app)  # 在 app.run() 前调用
# ============================================
def register_graph_routes(app):
    """
    将图推理路由注册到 FastAPI 应用
    
    使用方式：
        from graph_inference import register_graph_routes
        register_graph_routes(app)
    
    Args:
        app: FastAPI 应用实例
    """
    app.include_router(router)
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("⏳ Initializing graph models on startup...")
        if init_graph_models():
            logger.info("✅ Graph models initialized successfully")
        else:
            logger.warning("⚠️ Graph models initialization had issues, will retry on first request")
