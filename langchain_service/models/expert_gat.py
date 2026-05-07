"""
专家协作图 GAT（Graph Attention Network）模块

功能：
  1. 基于关键指标簇，推导涉及的医学科室
  2. 在科室协作图上计算专家调度权重
  3. 输出建议调用的 Agent 列表及其优先级
"""

import logging
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)


class ExpertGAT:
    """专家协作图神经网络推理引擎"""

    def __init__(
        self,
        expert_graph: nx.DiGraph,
        indicator_dept_mapping: Dict[str, List[Tuple[str, float]]],
    ):
        self.graph = expert_graph
        self.indicator_dept_mapping = indicator_dept_mapping
        self.agent_to_dept = self._build_agent_dept_mapping()

    @staticmethod
    def _build_agent_dept_mapping() -> Dict[str, str]:
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
        dept_scores = {}

        for indicator in key_indicators:
            if indicator not in self.indicator_dept_mapping:
                logger.warning("Indicator %s not found in mapping", indicator)
                continue

            for dept, relevance_score in self.indicator_dept_mapping[indicator]:
                if dept not in dept_scores:
                    dept_scores[dept] = []
                dept_scores[dept].append(relevance_score)

        dept_weights = {}
        for dept, scores in dept_scores.items():
            dept_weights[dept] = max(scores) if scores else 0.5

        return dept_weights

    def compute_expert_attention(self, dept_weights: Dict[str, float]) -> Dict[str, float]:
        node_scores = dept_weights.copy()

        for _iteration in range(2):
            new_scores = {}

            for node in node_scores:
                if node not in self.graph.nodes():
                    new_scores[node] = node_scores[node]
                    continue

                self_contribution = node_scores[node] * 0.5

                predecessors = list(self.graph.predecessors(node))
                predecessor_scores = []
                for pred in predecessors:
                    edge_data = self.graph.get_edge_data(pred, node)
                    if edge_data and edge_data.get("relation_type") == "PRECEDES":
                        if pred in node_scores:
                            edge_weight = edge_data.get("weight", 0.5)
                            predecessor_scores.append(node_scores[pred] * edge_weight)

                predecessor_contribution = np.mean(predecessor_scores) * 0.3 if predecessor_scores else 0

                successors = list(self.graph.successors(node))
                collaborator_scores = []
                for succ in successors:
                    edge_data = self.graph.get_edge_data(node, succ)
                    if edge_data and edge_data.get("relation_type") == "COLLABORATE":
                        if succ in node_scores:
                            edge_weight = edge_data.get("weight", 0.5)
                            collaborator_scores.append(node_scores[succ] * edge_weight)

                collaborator_contribution = np.mean(collaborator_scores) * 0.2 if collaborator_scores else 0

                new_score = self_contribution + predecessor_contribution + collaborator_contribution
                new_scores[node] = min(new_score, 1.0)

            node_scores.update(new_scores)

        return node_scores

    def infer_expert_schedule(
        self,
        key_indicators: List[str],
        indicator_weights: Dict[str, float] = None,
        top_k: int = 3,
    ) -> Dict:
        logger.info("Running ExpertGAT inference with indicators: %s", key_indicators)

        dept_weights = self.map_indicators_to_departments(key_indicators)
        if not dept_weights:
            logger.warning("No departments mapped from key indicators")
            return {
                "recommended_agents": [],
                "agent_weights": {},
                "involved_departments": [],
                "collaboration_notes": [],
            }

        node_scores = self.compute_expert_attention(dept_weights)

        agent_weights = {}
        for node, score in node_scores.items():
            for agent_name, dept_name in self.agent_to_dept.items():
                if node == dept_name:
                    agent_weights[agent_name] = score
                    break
            if node in self.agent_to_dept:
                agent_weights[node] = score

        if not agent_weights:
            for dept, weight in dept_weights.items():
                for agent_name, dept_name in self.agent_to_dept.items():
                    if dept_name == dept:
                        agent_weights[agent_name] = weight
                        break

        sorted_agents = sorted(
            agent_weights.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]

        recommended_agents = [agent for agent, _score in sorted_agents]
        collaboration_notes = self._generate_collaboration_notes(recommended_agents, dept_weights)

        return {
            "recommended_agents": recommended_agents,
            "agent_weights": {agent: weight for agent, weight in sorted_agents},
            "involved_departments": list(dept_weights.keys()),
            "collaboration_notes": collaboration_notes,
        }

    def _generate_collaboration_notes(
        self,
        agents: List[str],
        dept_weights: Dict[str, float],
    ) -> List[str]:
        notes = []

        laboratory_agent = "LaboratoryExpert"
        if laboratory_agent in agents:
            notes.append("检验科是首要任务，获取完整的生化、血象数据是其他专家诊断的基础")

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
        indicator_weights: Dict[str, float] = None,
    ) -> Dict:
        logger.info("Running ExpertGAT forward pass")
        return self.infer_expert_schedule(key_indicators, indicator_weights)


__all__ = ["ExpertGAT"]
