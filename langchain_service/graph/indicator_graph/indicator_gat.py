"""
指标生理关联图 GAT（Graph Attention Network）模块

功能：
  1. 基于患者的化验值，在指标关联图上计算注意力权重
  2. 识别关键指标簇（通常是相关联的异常指标）
  3. 为专家路由提供指标约束信息
"""

import logging
from typing import Dict, List, Tuple, Set
import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)


class IndicatorGAT:
    """指标生理关联图神经网络推理引擎"""
    
    def __init__(self, indicator_graph: nx.DiGraph, reference_ranges: Dict = None):
        """
        初始化指标 GAT
        
        Args:
            indicator_graph: NetworkX 有向图，边权重表示关联强度
            reference_ranges: 各指标的正常范围参考值
        """
        self.graph = indicator_graph
        self.reference_ranges = reference_ranges or self._get_default_ranges()
    
    @staticmethod
    def _get_default_ranges() -> Dict[str, Tuple[float, float]]:
        """获取默认的指标正常范围（单位和具体值需根据实际情况调整）"""
        return {
            "Cr": (60, 110),      # 肌酐，单位 μmol/L
            "BUN": (2.5, 7.1),    # 尿素氮，单位 mmol/L
            "UA": (150, 420),     # 尿酸，单位 μmol/L
            "GLU": (3.9, 6.1),    # 血糖，单位 mmol/L
            "HbA1c": (0, 6.5),    # 糖化血红蛋白，单位 %
            "ALT": (0, 40),       # 丙氨酸转氨酶，单位 U/L
            "AST": (0, 40),       # 天冬氨酸转氨酶，单位 U/L
            "TBIL": (5.1, 20.5),  # 总胆红素，单位 μmol/L
            "RBC": (4.5, 5.5),    # 红细胞，单位 ×10^12/L
            "WBC": (4.5, 11),     # 白细胞，单位 ×10^9/L
            "PLT": (150, 400),    # 血小板，单位 ×10^9/L
            "Hb": (130, 175),     # 血红蛋白，单位 g/L
            "CK-MB": (0, 25),     # 肌酸激酶同工酶，单位 U/L
            "Troponin": (0, 0.04), # 肌钙蛋白，单位 ng/mL
            "BNP": (0, 100),      # B型钠尿肽，单位 pg/mL
        }
    
    def compute_abnormality_scores(self, patient_labs: Dict[str, float]) -> Dict[str, float]:
        """
        计算每个指标的异常程度分数（Z-score 的简化版本）
        
        Args:
            patient_labs: {指标名 -> 检测值}
        
        Returns:
            {指标名 -> 异常程度 [0, 1]}，1 表示严重异常，0 表示正常
        """
        abnormality_scores = {}
        
        for indicator, value in patient_labs.items():
            if indicator not in self.reference_ranges:
                # 未知指标默认为 0.1（轻度可疑）
                abnormality_scores[indicator] = 0.1
                continue
            
            low, high = self.reference_ranges[indicator]
            
            if value < low:
                # 偏低：距离下界越远，分数越高
                ratio = (low - value) / max(low * 0.2, 1)  # 归一化因子
                abnormality_scores[indicator] = min(ratio, 1.0)
            elif value > high:
                # 偏高：距离上界越远，分数越高
                ratio = (value - high) / max(high * 0.2, 1)
                abnormality_scores[indicator] = min(ratio, 1.0)
            else:
                # 在正常范围内
                abnormality_scores[indicator] = 0.0
        
        return abnormality_scores
    
    def compute_attention_weights(self, patient_labs: Dict[str, float]) -> Dict[str, float]:
        """
        基于图结构和患者数据，计算每个节点的注意力权重
        
        这是 GAT 的核心：不仅考虑指标本身的异常程度，
        还考虑其在图中与其他异常指标的关联关系。
        
        Args:
            patient_labs: 患者化验值字典
        
        Returns:
            {指标名 -> 注意力权重 [0, 1]}
        """
        # 第1步：计算各指标的异常程度
        abnormality_scores = self.compute_abnormality_scores(patient_labs)
        
        # 第2步：基于图的邻域传播（Message Passing）
        # 使用一个简化的 GAT 算法：节点的新权重 = 自身权重 + 邻域异常指标的加权平均
        attention_weights = abnormality_scores.copy()
        
        # 进行 K 次迭代（K=2，即看 2 跳內的邻域）
        for iteration in range(2):
            new_weights = {}
            
            for node in self.graph.nodes():
                if node not in abnormality_scores:
                    continue
                
                # 自身贡献（70%权重）
                self_contribution = abnormality_scores[node] * 0.7
                
                # 邻域贡献（30%权重）
                neighbors = list(self.graph.neighbors(node))
                if neighbors:
                    neighbor_scores = []
                    for neighbor in neighbors:
                        if neighbor in abnormality_scores:
                            edge_data = self.graph.get_edge_data(node, neighbor)
                            edge_weight = edge_data.get('weight', 0.5) if edge_data else 0.5
                            neighbor_scores.append(
                                abnormality_scores[neighbor] * edge_weight
                            )
                    
                    if neighbor_scores:
                        neighbor_contribution = np.mean(neighbor_scores) * 0.3
                    else:
                        neighbor_contribution = 0
                else:
                    neighbor_contribution = 0
                
                new_weights[node] = min(self_contribution + neighbor_contribution, 1.0)
            
            # 更新权重
            abnormality_scores.update(new_weights)
        
        # 归一化权重（使其和为 1）
        total_weight = sum(abnormality_scores.values())
        if total_weight > 0:
            attention_weights = {
                k: v / total_weight for k, v in abnormality_scores.items()
            }
        else:
            attention_weights = abnormality_scores
        
        return attention_weights
    
    def identify_key_clusters(
        self,
        patient_labs: Dict[str, float],
        top_k: int = 5,
        abnormality_threshold: float = 0.1
    ) -> Dict:
        """
        识别关键指标簇（Top-K 异常指标及其相关的指标）
        
        Args:
            patient_labs: 患者化验值
            top_k: 返回的关键簇数量
            abnormality_threshold: 异常阈值，低于此值的指标不参与聚类
        
        Returns:
            {
                'key_indicators': List[str],              # 关键指标列表
                'weights': Dict[str, float],              # 指标权重
                'clusters': List[Set[str]],               # 指标簇（相关联的指标组）
                'abnormality_scores': Dict[str, float],   # 异常程度分数
            }
        """
        attention_weights = self.compute_attention_weights(patient_labs)
        abnormality_scores = self.compute_abnormality_scores(patient_labs)
        
        # 过滤异常指标
        abnormal_indicators = {
            ind: score for ind, score in abnormality_scores.items()
            if score >= abnormality_threshold
        }
        
        if not abnormal_indicators:
            logger.warning("No abnormal indicators found in patient labs")
            return {
                'key_indicators': [],
                'weights': {},
                'clusters': [],
                'abnormality_scores': abnormality_scores,
            }
        
        # 按异常程度排序，取 Top-K
        sorted_indicators = sorted(
            abnormal_indicators.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        key_indicators = [ind for ind, _ in sorted_indicators]
        
        # 识别簇：对于每个关键指标，找其邻域的其他异常指标
        clusters = []
        for key_ind in key_indicators:
            cluster = {key_ind}  # 包含关键指标本身
            
            # BFS 找邻域
            neighbors = set(self.graph.neighbors(key_ind))
            reverse_neighbors = set(self.graph.predecessors(key_ind))
            all_neighbors = neighbors | reverse_neighbors
            
            for neighbor in all_neighbors:
                if neighbor in abnormal_indicators:
                    cluster.add(neighbor)
            
            clusters.append(cluster)
        
        return {
            'key_indicators': key_indicators,
            'weights': {ind: attention_weights.get(ind, 0) for ind in key_indicators},
            'clusters': clusters,
            'abnormality_scores': abnormality_scores,
        }
    
    def forward(self, patient_labs: Dict[str, float]) -> Dict:
        """
        前向推理：从患者化验值到关键指标簇的完整推理过程
        
        Args:
            patient_labs: 患者化验值
        
        Returns:
            推理结果字典
        """
        logger.info(f"Running IndicatorGAT forward pass with {len(patient_labs)} indicators")
        return self.identify_key_clusters(patient_labs)
