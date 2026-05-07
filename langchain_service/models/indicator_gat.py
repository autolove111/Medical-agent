"""
指标生理关联图 GAT（Graph Attention Network）模块

功能：
  1. 基于患者的化验值，在指标关联图上计算注意力权重
  2. 识别关键指标簇（通常是相关联的异常指标）
  3. 为专家路由提供指标约束信息
"""

import logging
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)


class IndicatorGAT:
    """指标生理关联图神经网络推理引擎"""

    def __init__(self, indicator_graph: nx.DiGraph, reference_ranges: Dict = None):
        self.graph = indicator_graph
        self.reference_ranges = reference_ranges or self._get_default_ranges()

    @staticmethod
    def _get_default_ranges() -> Dict[str, Tuple[float, float]]:
        return {
            "Cr": (60, 110),
            "BUN": (2.5, 7.1),
            "UA": (150, 420),
            "GLU": (3.9, 6.1),
            "HbA1c": (0, 6.5),
            "ALT": (0, 40),
            "AST": (0, 40),
            "TBIL": (5.1, 20.5),
            "RBC": (4.5, 5.5),
            "WBC": (4.5, 11),
            "PLT": (150, 400),
            "Hb": (130, 175),
            "CK-MB": (0, 25),
            "Troponin": (0, 0.04),
            "BNP": (0, 100),
        }

    def compute_abnormality_scores(self, patient_labs: Dict[str, float]) -> Dict[str, float]:
        abnormality_scores = {}

        for indicator, value in patient_labs.items():
            if indicator not in self.reference_ranges:
                abnormality_scores[indicator] = 0.1
                continue

            low, high = self.reference_ranges[indicator]

            if value < low:
                ratio = (low - value) / max(low * 0.2, 1)
                abnormality_scores[indicator] = min(ratio, 1.0)
            elif value > high:
                ratio = (value - high) / max(high * 0.2, 1)
                abnormality_scores[indicator] = min(ratio, 1.0)
            else:
                abnormality_scores[indicator] = 0.0

        return abnormality_scores

    def compute_attention_weights(self, patient_labs: Dict[str, float]) -> Dict[str, float]:
        abnormality_scores = self.compute_abnormality_scores(patient_labs)
        attention_weights = abnormality_scores.copy()

        for _iteration in range(2):
            new_weights = {}

            for node in self.graph.nodes():
                if node not in abnormality_scores:
                    continue

                self_contribution = abnormality_scores[node] * 0.7
                neighbors = list(self.graph.neighbors(node))
                if neighbors:
                    neighbor_scores = []
                    for neighbor in neighbors:
                        if neighbor in abnormality_scores:
                            edge_data = self.graph.get_edge_data(node, neighbor)
                            edge_weight = edge_data.get("weight", 0.5) if edge_data else 0.5
                            neighbor_scores.append(abnormality_scores[neighbor] * edge_weight)

                    neighbor_contribution = np.mean(neighbor_scores) * 0.3 if neighbor_scores else 0
                else:
                    neighbor_contribution = 0

                new_weights[node] = min(self_contribution + neighbor_contribution, 1.0)

            abnormality_scores.update(new_weights)

        total_weight = sum(abnormality_scores.values())
        if total_weight > 0:
            attention_weights = {
                key: value / total_weight for key, value in abnormality_scores.items()
            }
        else:
            attention_weights = abnormality_scores

        return attention_weights

    def identify_key_clusters(
        self,
        patient_labs: Dict[str, float],
        top_k: int = 5,
        abnormality_threshold: float = 0.1,
    ) -> Dict:
        attention_weights = self.compute_attention_weights(patient_labs)
        abnormality_scores = self.compute_abnormality_scores(patient_labs)

        abnormal_indicators = {
            indicator: score
            for indicator, score in abnormality_scores.items()
            if score >= abnormality_threshold
        }

        if not abnormal_indicators:
            logger.warning("No abnormal indicators found in patient labs")
            return {
                "key_indicators": [],
                "weights": {},
                "clusters": [],
                "abnormality_scores": abnormality_scores,
            }

        sorted_indicators = sorted(
            abnormal_indicators.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]

        key_indicators = [indicator for indicator, _score in sorted_indicators]

        clusters = []
        for key_ind in key_indicators:
            cluster = {key_ind}
            neighbors = set(self.graph.neighbors(key_ind))
            reverse_neighbors = set(self.graph.predecessors(key_ind))
            all_neighbors = neighbors | reverse_neighbors

            for neighbor in all_neighbors:
                if neighbor in abnormal_indicators:
                    cluster.add(neighbor)

            clusters.append(cluster)

        return {
            "key_indicators": key_indicators,
            "weights": {indicator: attention_weights.get(indicator, 0) for indicator in key_indicators},
            "clusters": clusters,
            "abnormality_scores": abnormality_scores,
        }

    def forward(self, patient_labs: Dict[str, float]) -> Dict:
        logger.info("Running IndicatorGAT forward pass with %d indicators", len(patient_labs))
        return self.identify_key_clusters(patient_labs)


__all__ = ["IndicatorGAT"]
