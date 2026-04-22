"""
专家协作图 GAT（Graph Attention Network）模块

功能：
  1. 基于关键指标簇，推导涉及的医学科室
  2. 在科室协作图上计算专家调度权重
  3. 输出建议调用的 Agent 列表及其优先级
"""

import logging
from typing import Dict, List, Tuple, Set
import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)


class ExpertGAT:
    """专家协作图神经网络推理引擎"""
    
    def __init__(
        self,
        expert_graph: nx.DiGraph,
        indicator_dept_mapping: Dict[str, List[Tuple[str, float]]]
    ):
        """
        初始化专家 GAT
        
        Args:
            expert_graph: NetworkX 有向图，表示科室/Agent 的协作关系
            indicator_dept_mapping: 指标到科室的映射 {指标名 -> [(科室名, 相关度), ...]}
        """
        self.graph = expert_graph
        self.indicator_dept_mapping = indicator_dept_mapping
        
        # 构建 Agent 到科室的映射
        self.agent_to_dept = self._build_agent_dept_mapping()
    
    @staticmethod
    def _build_agent_dept_mapping() -> Dict[str, str]:
        """
        构建从 Agent 名称到科室名称的映射
        
        Returns:
            Dict: {AgentName -> DepartmentName}
        """
        return {
            "RenalExpert": "RenalDepartment",
            "CardiologyExpert": "CardiologyDepartment",
            "HematologyExpert": "HematologyDepartment",
            "InfectiousExpert": "InfectiousDepartment",
            "EndocrinologyExpert": "EndocrinologyDepartment",
            "RespiratoryExpert": "RespiratoryDepartment",
            "GastroenterologyExpert": "GastroenterologyDepartment",
            "NeurologicalExpert": "NeurologicalDepartment",
            "LaboratoryExpert": "LaboratoryDepartment",
        }
    
    def map_indicators_to_departments(self, key_indicators: List[str]) -> Dict[str, float]:
        """
        基于指标关联，推导相关的科室及其权重
        
        Args:
            key_indicators: 关键指标列表
        
        Returns:
            Dict: {科室名 -> 权重 [0, 1]}
        """
        dept_scores = {}
        
        for indicator in key_indicators:
            if indicator not in self.indicator_dept_mapping:
                logger.warning(f"Indicator {indicator} not found in mapping")
                continue
            
            # 获取该指标关联的所有科室
            for dept, relevance_score in self.indicator_dept_mapping[indicator]:
                if dept not in dept_scores:
                    dept_scores[dept] = []
                dept_scores[dept].append(relevance_score)
        
        # 对每个科室，取其相关指标的最大相关度分数
        dept_weights = {}
        for dept, scores in dept_scores.items():
            dept_weights[dept] = max(scores) if scores else 0.5
        
        return dept_weights
    
    def compute_expert_attention(self, dept_weights: Dict[str, float]) -> Dict[str, float]:
        """
        基于科室权重和专家协作图，计算 Agent 的调用权重
        
        这是第二层 GAT：基于第一层 GAT 得到的科室权重，结合专家协作关系，
        计算最终的 Agent 调度权重。
        
        Args:
            dept_weights: {科室名 -> 权重}
        
        Returns:
            {科室名 或 Agent名 -> 最终权重}
        """
        # 初始：直接使用科室权重
        node_scores = dept_weights.copy()
        
        # 两层 GAT 迭代
        for iteration in range(2):
            new_scores = {}
            
            for node in node_scores:
                if node not in self.graph.nodes():
                    new_scores[node] = node_scores[node]
                    continue
                
                # 自身贡献（50%）
                self_contribution = node_scores[node] * 0.5
                
                # 前置依赖贡献：如果有前置节点，增强权重（30%）
                predecessors = list(self.graph.predecessors(node))
                predecessor_scores = []
                for pred in predecessors:
                    edge_data = self.graph.get_edge_data(pred, node)
                    if edge_data and edge_data.get('relation_type') == 'PRECEDES':
                        if pred in node_scores:
                            edge_weight = edge_data.get('weight', 0.5)
                            predecessor_scores.append(node_scores[pred] * edge_weight)
                
                if predecessor_scores:
                    predecessor_contribution = np.mean(predecessor_scores) * 0.3
                else:
                    predecessor_contribution = 0
                
                # 协作伙伴贡献（20%）
                successors = list(self.graph.successors(node))
                collaborator_scores = []
                for succ in successors:
                    edge_data = self.graph.get_edge_data(node, succ)
                    if edge_data and edge_data.get('relation_type') == 'COLLABORATE':
                        if succ in node_scores:
                            edge_weight = edge_data.get('weight', 0.5)
                            collaborator_scores.append(node_scores[succ] * edge_weight)
                
                if collaborator_scores:
                    collaborator_contribution = np.mean(collaborator_scores) * 0.2
                else:
                    collaborator_contribution = 0
                
                new_score = self_contribution + predecessor_contribution + collaborator_contribution
                new_scores[node] = min(new_score, 1.0)
            
            node_scores.update(new_scores)
        
        return node_scores
    
    def infer_expert_schedule(
        self,
        key_indicators: List[str],
        indicator_weights: Dict[str, float] = None,
        top_k: int = 3
    ) -> Dict:
        """
        从关键指标簇推导推荐的 Agent 调度方案
        
        Args:
            key_indicators: 关键指标列表
            indicator_weights: 指标权重字典（可选，用于加权）
            top_k: 返回的推荐 Agent 数量
        
        Returns:
            {
                'recommended_agents': List[str],           # 推荐 Agent 列表
                'agent_weights': Dict[str, float],         # Agent 权重
                'involved_departments': List[str],         # 涉及的科室
                'collaboration_notes': List[str],          # 协作备注
            }
        """
        logger.info(f"Running ExpertGAT inference with indicators: {key_indicators}")
        
        # 第1步：推导涉及的科室
        dept_weights = self.map_indicators_to_departments(key_indicators)
        if not dept_weights:
            logger.warning("No departments mapped from key indicators")
            return {
                'recommended_agents': [],
                'agent_weights': {},
                'involved_departments': [],
                'collaboration_notes': [],
            }
        
        # 第2步：计算专家注意力权重
        node_scores = self.compute_expert_attention(dept_weights)
        
        # 第3步：提取 Agent 权重（去掉科室前缀，如果有的话）
        agent_weights = {}
        for node, score in node_scores.items():
            # 如果节点对应一个 Agent（在 agent_to_dept 映射中）
            for agent_name, dept_name in self.agent_to_dept.items():
                if node == dept_name:
                    agent_weights[agent_name] = score
                    break
            # 否则如果节点本身就是 Agent 名称
            if node in self.agent_to_dept:
                agent_weights[node] = score
        
        # 如果没有找到任何 Agent，则根据科室权重创建默认 Agent
        if not agent_weights:
            for dept, weight in dept_weights.items():
                for agent_name, dept_name in self.agent_to_dept.items():
                    if dept_name == dept:
                        agent_weights[agent_name] = weight
                        break
        
        # 第4步：按权重排序，取 Top-K
        sorted_agents = sorted(
            agent_weights.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        recommended_agents = [agent for agent, _ in sorted_agents]
        
        # 第5步：生成协作备注
        collaboration_notes = self._generate_collaboration_notes(
            recommended_agents,
            dept_weights
        )
        
        return {
            'recommended_agents': recommended_agents,
            'agent_weights': {agent: weight for agent, weight in sorted_agents},
            'involved_departments': list(dept_weights.keys()),
            'collaboration_notes': collaboration_notes,
        }
    
    def _generate_collaboration_notes(
        self,
        agents: List[str],
        dept_weights: Dict[str, float]
    ) -> List[str]:
        """
        生成专家协作的人性化备注
        
        Args:
            agents: Agent 列表
            dept_weights: 科室权重
        
        Returns:
            List[str]: 备注列表
        """
        notes = []
        
        # 检查是否有前置依赖（如检验科）
        laboratory_agent = "LaboratoryExpert"
        if laboratory_agent in agents:
            notes.append(f"检验科是首要任务，获取完整的生化、血象数据是其他专家诊断的基础")
        
        # 检查是否有协作关系
        if len(agents) > 1:
            if "RenalExpert" in agents and "CardiologyExpert" in agents:
                notes.append("肾内科与心内科需协作：考虑肾源性高血压或心肾综合征")
            
            if "RenalExpert" in agents and "EndocrinologyExpert" in agents:
                notes.append("肾内科与内分泌科需协作：排除糖尿病肾病")
            
            if "HematologyExpert" in agents and "InfectiousExpert" in agents:
                notes.append("血液科与感染科需协作：评估感染相关的血象异常")
        
        return notes
    
    def forward(
        self,
        key_indicators: List[str],
        indicator_weights: Dict[str, float] = None
    ) -> Dict:
        """
        前向推理：从关键指标到 Agent 调度方案的完整过程
        
        Args:
            key_indicators: 关键指标列表
            indicator_weights: 指标权重（可选）
        
        Returns:
            推理结果字典
        """
        logger.info(f"Running ExpertGAT forward pass")
        return self.infer_expert_schedule(key_indicators, indicator_weights)
