"""
科室协作关系矩阵 - 定义科室间的诊疗协作需求

核心理念：
  - 当肾内科诊断出"糖尿病肾病"时，不仅肾内科权重提升
  - 内分泌科的权重也应该被"拉动"提升（因为需要确认血糖控制）
  - 这是一个动态的、基于诊断结果的协作系统
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CollaborationEdge:
    """科室间协作边"""
    from_dept: str              # 从哪个科室出发
    to_dept: str                # 协作到哪个科室
    base_strength: float        # 基础协作强度（0.1-1.0）
    trigger_keywords: List[str] # 触发关键词（如诊断中包含这些词，就启动协作）
    collaboration_reason: str   # 为什么需要协作


class DepartmentCollaborationGraph:
    """科室协作关系图"""
    
    def __init__(self):
        """初始化科室协作关系"""
        
        # 定义所有协作关系（有向图）
        self.collaboration_edges: List[CollaborationEdge] = [
            # 肾内科的协作
            CollaborationEdge(
                from_dept="肾内科",
                to_dept="内分泌科",
                base_strength=0.6,
                trigger_keywords=["糖尿病肾病", "代谢", "高血糖"],
                collaboration_reason="确认血糖控制、排除糖尿病"
            ),
            CollaborationEdge(
                from_dept="肾内科",
                to_dept="心内科",
                base_strength=0.5,
                trigger_keywords=["高血压", "心脏", "电解质失衡"],
                collaboration_reason="评估心脏负荷、控制血压"
            ),
            CollaborationEdge(
                from_dept="肾内科",
                to_dept="血液科",
                base_strength=0.4,
                trigger_keywords=["贫血", "凝血", "血小板"],
                collaboration_reason="评估慢性肾病贫血"
            ),
            
            # 内分泌科的协作
            CollaborationEdge(
                from_dept="内分泌科",
                to_dept="肾内科",
                base_strength=0.7,
                trigger_keywords=["糖尿病肾病", "肾功能", "蛋白尿"],
                collaboration_reason="评估肾脏损伤程度"
            ),
            CollaborationEdge(
                from_dept="内分泌科",
                to_dept="心内科",
                base_strength=0.6,
                trigger_keywords=["代谢综合征", "高血压", "心血管风险"],
                collaboration_reason="评估心血管风险"
            ),
            
            # 血液科的协作
            CollaborationEdge(
                from_dept="血液科",
                to_dept="肾内科",
                base_strength=0.55,
                trigger_keywords=["贫血", "慢性病贫血"],
                collaboration_reason="评估肾性贫血"
            ),
            
            # 肝胆病科的协作
            CollaborationEdge(
                from_dept="肝胆病科",
                to_dept="感染科",
                base_strength=0.6,
                trigger_keywords=["病毒性肝炎", "感染"],
                collaboration_reason="确认肝炎类型、传播风险"
            ),
        ]
        
        logger.info(f"【协作图初始化】共 {len(self.collaboration_edges)} 条协作边")
    
    def get_triggered_collaborations(
        self,
        from_dept: str,
        diagnosis: str,
        confidence: float
    ) -> Dict[str, float]:
        """
        基于科室诊断结果，找出该触发的协作关系
        
        Args:
            from_dept: 诊断科室
            diagnosis: 诊断结果文本
            confidence: 诊断置信度
        
        Returns:
            {目标科室: 协作推动权重}
        """
        triggered = {}
        
        for edge in self.collaboration_edges:
            if edge.from_dept != from_dept:
                continue
            
            # 检查诊断文本是否包含触发关键词
            for keyword in edge.trigger_keywords:
                if keyword in diagnosis:
                    # 协作推动权重 = 基础强度 × 诊断置信度 × 1.2（协作倍增因子）
                    collaboration_weight = edge.base_strength * confidence * 1.2
                    
                    if edge.to_dept not in triggered:
                        triggered[edge.to_dept] = 0.0
                    
                    triggered[edge.to_dept] = max(triggered[edge.to_dept], collaboration_weight)
                    
                    logger.info(f"【协作触发】{from_dept} 的诊断 '{keyword}' "
                               f"触发了对 {edge.to_dept} 的协作 "
                               f"(推动权重: {collaboration_weight:.3f})")
                    break
        
        return triggered
    
    def visualize_collaboration_graph(self) -> str:
        """生成协作图的文本可视化"""
        visualization = "【科室协作关系图】\n"
        
        dept_map = {}
        for edge in self.collaboration_edges:
            if edge.from_dept not in dept_map:
                dept_map[edge.from_dept] = []
            dept_map[edge.from_dept].append(edge)
        
        for dept, edges in dept_map.items():
            visualization += f"\n{dept}:\n"
            for edge in edges:
                visualization += f"  → {edge.to_dept} "
                visualization += f"(强度: {edge.base_strength:.1f}) "
                visualization += f"[{', '.join(edge.trigger_keywords)}]\n"
                visualization += f"    原因: {edge.collaboration_reason}\n"
        
        return visualization


# 全局协作图
COLLABORATION_GRAPH = DepartmentCollaborationGraph()


def get_collaboration_boost(
    from_dept: str,
    diagnosis: str,
    confidence: float
) -> Dict[str, float]:
    """
    获取协作推动（这是在 GAT 更新时调用的）
    
    Args:
        from_dept: 诊断科室
        diagnosis: 诊断结果
        confidence: 置信度
    
    Returns:
        各科室的协作推动权重
    """
    return COLLABORATION_GRAPH.get_triggered_collaborations(from_dept, diagnosis, confidence)


if __name__ == "__main__":
    # 测试
    graph = DepartmentCollaborationGraph()
    
    print(graph.visualize_collaboration_graph())
    
    print("\n【测试协作触发】")
    print("="*60)
    
    # 测试 1：肾内科诊断糖尿病肾病
    collab1 = get_collaboration_boost(
        from_dept="肾内科",
        diagnosis="慢性肾脏病（CKD）Stage 3-4，伴糖尿病肾病风险",
        confidence=0.85
    )
    print(f"\n肾内科诊断结果触发的协作:\n{collab1}")
    
    # 测试 2：内分泌科诊断糖尿病
    collab2 = get_collaboration_boost(
        from_dept="内分泌科",
        diagnosis="糖尿病（血糖升高），需评估肾脏损伤",
        confidence=0.80
    )
    print(f"\n内分泌科诊断结果触发的协作:\n{collab2}")
