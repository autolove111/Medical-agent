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

from .graph_utils import GraphLoader

try:
    from experimental.indicator_gat import IndicatorGAT
except ImportError as e:
    logging.warning(f"IndicatorGAT not found: {e}")
    IndicatorGAT = None

try:
    from experimental.expert_gat import ExpertGAT
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
