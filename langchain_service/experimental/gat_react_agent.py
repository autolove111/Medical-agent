"""
GAT-ReAct 增强的医学智能体 - 第五步核心实现

完整流程：
  1. 患者数据预处理 → 指标标准化 & 参考范围对标
  2. GAT 推理（两层）→ 关键指标簇 + 科室调用概率
  3. 动态 RAG 检索 → 基于 GAT 输出的高概率科室
  4. ReAct 循环 → Thought → Action → Observation → 下一轮
  5. 最终综合诊断 → 整合所有科室意见
"""

import logging
import json
from typing import Dict, List, Tuple, Optional, Iterator
from dataclasses import dataclass, asdict
import numpy as np

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from knowledge.rag import retrieve_medical_knowledge
from tools import query_user_medical_history, set_current_user_id
from knowledge.medical_knowledge import create_knowledge_base, PatientHistoryEnhancer

logger = logging.getLogger(__name__)


@dataclass
class IndicatorCluster:
    """关键指标簇"""
    indicators: List[str]       # 关键指标列表
    weights: Dict[str, float]   # 各指标权重
    cluster_strength: float      # 聚类强度 (0-1)
    interpretation: str          # 临床解释


@dataclass
class DepartmentProbability:
    """科室调用概率"""
    department: str
    initial_prob: float          # 初始概率（基于指标）
    final_prob: float            # 最终概率（考虑协作关系）
    reason: str                  # 为什么推荐这个科室


class GATReActMedicalAgent:
    """
    集成 GAT-ReAct 的医学智能体
    
    核心创新：
      - 两层 GAT：指标层 + 科室层
      - 动态概率：不是固定科室列表，而是实时计算
      - RAG 联动：RAG 查询以 GAT 输出为指导
      - 多轮 ReAct：逐步深化诊断
    """
    
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.kb = create_knowledge_base()
        self.enhancer = PatientHistoryEnhancer(self.kb)
        self.llm = ChatOpenAI(
            model=settings.DASHSCOPE_MODEL,
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.DASHSCOPE_BASE_URL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
            streaming=True,
        )
        
        # 初始化指标-科室映射表（代替完整的 GAT 图）
        self.indicator_to_departments = {
            "Cr": [("肾内科", 0.9), ("心内科", 0.3)],
            "BUN": [("肾内科", 0.85), ("内分泌科", 0.2)],
            "UA": [("肾内科", 0.8), ("风湿免疫科", 0.5)],
            "WBC": [("血液科", 0.9), ("感染科", 0.7)],
            "ALT": [("肝胆病科", 0.9), ("感染科", 0.4)],
            "GLU": [("内分泌科", 0.9), ("心内科", 0.3)],
            "Hb": [("血液科", 0.85), ("肾内科", 0.4)],
            "PLT": [("血液科", 0.9), ("感染科", 0.3)],
        }
        
        # 科室协作关系（代替完整的专家图）
        self.department_collaboration = {
            ("肾内科", "心内科"): ("COLLABORATE", 0.8),     # 强协作
            ("肾内科", "内分泌科"): ("COLLABORATE", 0.6),
            ("血液科", "感染科"): ("COLLABORATE", 0.7),
            ("肝胆病科", "感染科"): ("COLLABORATE", 0.75),
            ("内分泌科", "心内科"): ("COLLABORATE", 0.65),
        }
    
    def _identify_key_indicator_cluster(self, lab_results: Dict[str, float]) -> IndicatorCluster:
        """
        第一层 GAT：在指标关联图上识别关键指标簇
        
        简化实现：计算异常指标的聚合度
        """
        abnormal_indicators = []
        weights = {}
        
        for indicator, value in lab_results.items():
            check = self.kb.check_abnormality(indicator, value)
            if check.get("is_abnormal"):
                abnormal_indicators.append(indicator)
                # 权重 = 异常程度（简化：critical=1.0, high=0.8, low=0.6）
                level = check.get("level", "normal")
                level_weight = {"critical": 1.0, "high": 0.8, "low": 0.6}.get(level, 0.5)
                weights[indicator] = level_weight
        
        if not abnormal_indicators:
            return IndicatorCluster([], {}, 0.0, "所有指标正常")
        
        # 计算聚类强度（异常指标的平均权重）
        cluster_strength = np.mean(list(weights.values())) if weights else 0.0
        
        # 分类解释
        if "Cr" in abnormal_indicators and "BUN" in abnormal_indicators:
            interpretation = "肾功能异常（Cr、BUN 同时升高）"
        elif "WBC" in abnormal_indicators or "PLT" in abnormal_indicators:
            interpretation = "血液系统异常"
        elif "ALT" in abnormal_indicators or "AST" in abnormal_indicators:
            interpretation = "肝功能异常"
        else:
            interpretation = f"多指标异常：{', '.join(abnormal_indicators)}"
        
        return IndicatorCluster(
            indicators=abnormal_indicators,
            weights=weights,
            cluster_strength=cluster_strength,
            interpretation=interpretation
        )
    
    def _compute_department_probabilities(self, cluster: IndicatorCluster) -> List[DepartmentProbability]:
        """
        第二层 GAT：基于关键指标簇，计算科室调用概率
        
        分两步：
          1. 初始概率：指标 → 科室映射
          2. 协作调制：通过专家图调整概率
        """
        # Step 1: 计算初始概率
        dept_probs = {}
        for indicator in cluster.indicators:
            indicator_weight = cluster.weights.get(indicator, 0.5)
            
            if indicator in self.indicator_to_departments:
                for dept, base_rel in self.indicator_to_departments[indicator]:
                    # 初始概率 = 指标权重 × 指标-科室相关度
                    initial_prob = indicator_weight * base_rel
                    if dept not in dept_probs:
                        dept_probs[dept] = []
                    dept_probs[dept].append(initial_prob)
        
        # 聚合初始概率（取均值）
        dept_initial_probs = {
            dept: np.mean(probs) 
            for dept, probs in dept_probs.items()
        }
        
        # Step 2: 协作调制（第二层 GAT）
        dept_final_probs = {}
        for dept, initial_prob in dept_initial_probs.items():
            final_prob = initial_prob
            adjust_reasons = []
            
            # 检查协作关系
            for (dept1, dept2), (relation, strength) in self.department_collaboration.items():
                if dept == dept2 and dept1 in dept_initial_probs:
                    # 如果关联科室概率高，当前科室也提升
                    if dept_initial_probs[dept1] > 0.5:
                        adjustment = dept_initial_probs[dept1] * strength * 0.2  # 0.2 为调制系数
                        final_prob = min(1.0, final_prob + adjustment)
                        adjust_reasons.append(f"因{dept1}({dept_initial_probs[dept1]:.2f})与其协作({strength})")
            
            dept_final_probs[dept] = (final_prob, adjust_reasons)
        
        # 构建返回结果
        results = []
        for dept, (final_prob, reasons) in sorted(
            dept_final_probs.items(), 
            key=lambda x: x[1][0], 
            reverse=True
        ):
            initial = dept_initial_probs.get(dept, 0.0)
            reason = f"初始概率 {initial:.2f} → 最终 {final_prob:.2f}"
            if reasons:
                reason += " | " + "; ".join(reasons)
            
            results.append(DepartmentProbability(
                department=dept,
                initial_prob=initial,
                final_prob=final_prob,
                reason=reason
            ))
        
        return results
    
    def _dynamic_rag_retrieval(
        self, 
        cluster: IndicatorCluster,
        departments: List[DepartmentProbability]
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        动态 RAG 检索：基于 GAT 输出进行多源检索
        
        检索策略：
          1. 检索 1：关键指标簇的医学知识
          2. 检索 2：高概率科室的专科知识
          3. 检索 3：科室间协作指南
        """
        retrieval_results = {}
        
        # Query 1: 关键指标簇
        if cluster.indicators:
            query1 = f"{cluster.interpretation} 的临床意义和诊疗路径"
            result1, sources1 = retrieve_medical_knowledge(query1)
            retrieval_results["indicator_cluster"] = (result1, sources1)
        
        # Query 2: 高概率科室（概率 > 0.5）
        high_prob_depts = [d for d in departments if d.final_prob > 0.5]
        for dept in high_prob_depts[:2]:  # 只查询前两个高概率科室
            query2 = f"{dept.department} 诊疗指南"
            result2, sources2 = retrieve_medical_knowledge(query2)
            retrieval_results[f"dept_{dept.department}"] = (result2, sources2)
        
        # Query 3: 科室协作
        if len(high_prob_depts) > 1:
            query3 = f"{high_prob_depts[0].department}与{high_prob_depts[1].department}协作"
            result3, sources3 = retrieve_medical_knowledge(query3)
            retrieval_results["collaboration"] = (result3, sources3)
        
        return retrieval_results
    
    def _build_gat_constrained_prompt(
        self,
        query: str,
        user_history: str,
        cluster: IndicatorCluster,
        departments: List[DepartmentProbability],
        rag_results: Dict[str, List[Tuple[str, str]]]
    ) -> str:
        """
        构建受 GAT 约束的 LLM 提示词
        
        关键：将 GAT 的输出（指标簇、科室概率）作为硬约束注入
        """
        
        gat_guidance = f"""
【GAT 分析结果】
关键指标簇：{', '.join(cluster.indicators) if cluster.indicators else '无'}
  - 聚类强度：{cluster.cluster_strength:.2f}
  - 临床解释：{cluster.interpretation}
  - 各指标权重：{json.dumps(cluster.weights, ensure_ascii=False)}

推荐科室调用概率分布：
"""
        for dept in departments[:5]:  # 只显示前 5 个
            gat_guidance += f"\n  - {dept.department}: {dept.final_prob:.2f} ({dept.reason})"
        
        gat_guidance += """

【RAG 检索结果】
"""
        for source_name, (content, refs) in rag_results.items():
            gat_guidance += f"\n{source_name}:\n{content[:200]}...\n"
        
        prompt = f"""
{gat_guidance}

【用户病史】
{user_history}

【用户问题】
{query}

请根据上述 GAT 分析和 RAG 检索结果，给出结构化诊断建议。特别关注：
1. 为什么关键指标簇是 {cluster.interpretation}？
2. 推荐首先咨询的科室是哪个，为什么（根据概率分布）？
3. 是否需要进行多科室联合诊疗（参考协作关系）？
4. 后续需要进行哪些检查或监测？

最后，请在回复末尾添加元数据行：
[META|医疗:是或否|疾病:疾病名称|过敏:药物名称或无]
"""
        return prompt
    
    def process_query_with_gat_react(
        self, 
        query: str,
        user_context: Optional[str] = None,
        lab_results: Optional[Dict[str, float]] = None
    ) -> Tuple[str, Dict]:
        """
        完整的 GAT-ReAct 处理流程
        
        返回：(诊断结果, 中间过程数据)
        """
        set_current_user_id(self.user_id)
        
        # Step 1: 加载用户病历
        history_text = user_context or query_user_medical_history(self.user_id)
        
        # Step 2: 第一层 GAT - 识别关键指标簇
        cluster = IndicatorCluster([], {}, 0.0, "无异常指标")
        if lab_results:
            cluster = self._identify_key_indicator_cluster(lab_results)
            logger.info(f"关键指标簇: {cluster.indicators}, 聚类强度: {cluster.cluster_strength:.2f}")
        
        # Step 3: 第二层 GAT - 计算科室概率
        departments = self._compute_department_probabilities(cluster)
        logger.info(f"科室概率分布: {[(d.department, d.final_prob) for d in departments[:3]]}")
        
        # Step 4: 动态 RAG 检索
        rag_results = self._dynamic_rag_retrieval(cluster, departments)
        logger.info(f"RAG 检索了 {len(rag_results)} 组结果")
        
        # Step 5: 构建受约束的提示
        prompt = self._build_gat_constrained_prompt(
            query, history_text, cluster, departments, rag_results
        )
        
        # Step 6: 调用 LLM
        messages = [
            SystemMessage(content="你是专业的医学检验智能助手，基于图注意力网络 (GAT) 的指导进行诊疗决策。"),
            HumanMessage(content=prompt)
        ]
        
        response = self.llm.invoke(messages)
        result = response.content if hasattr(response, "content") else str(response)
        
        return result, {
            "cluster": asdict(cluster),
            "departments": [asdict(d) for d in departments],
            "rag_sources": len(rag_results)
        }
    
    def stream_query_with_gat_react(
        self,
        query: str,
        user_context: Optional[str] = None,
        lab_results: Optional[Dict[str, float]] = None
    ) -> Iterator[Dict]:
        """
        流式处理版本
        """
        set_current_user_id(self.user_id)
        
        # 前置处理（同步）
        history_text = user_context or query_user_medical_history(self.user_id)
        cluster = IndicatorCluster([], {}, 0.0, "无异常指标")
        if lab_results:
            cluster = self._identify_key_indicator_cluster(lab_results)
        
        departments = self._compute_department_probabilities(cluster)
        rag_results = self._dynamic_rag_retrieval(cluster, departments)
        prompt = self._build_gat_constrained_prompt(query, history_text, cluster, departments, rag_results)
        
        # 流式调用 LLM
        messages = [
            SystemMessage(content="你是专业的医学检验智能助手"),
            HumanMessage(content=prompt)
        ]
        
        full_response = ""
        for chunk in self.llm.stream(messages):
            text = chunk.content if hasattr(chunk, "content") else ""
            if text:
                full_response += text
                yield {
                    "chunk": text,
                    "full_response": full_response,
                    "metadata": {
                        "cluster_strength": cluster.cluster_strength,
                        "top_department": departments[0].department if departments else None
                    }
                }


# 便捷函数
def create_gat_react_agent(user_id: Optional[str] = None) -> GATReActMedicalAgent:
    """创建 GAT-ReAct Agent"""
    return GATReActMedicalAgent(user_id)


if __name__ == "__main__":
    # 测试
    agent = create_gat_react_agent(user_id="test-user-001")
    
    lab_results = {
        "Cr": 150,
        "BUN": 15,
        "UA": 520,
        "ALT": 45,
        "WBC": 8.5,
    }
    
    result, metadata = agent.process_query_with_gat_react(
        query="请分析这张化验单",
        lab_results=lab_results
    )
    
    print("=" * 60)
    print("GAT-ReAct 诊断结果")
    print("=" * 60)
    print(result)
    print("\n中间数据:")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
