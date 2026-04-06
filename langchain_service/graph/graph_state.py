from typing import TypedDict, List, Dict, Any

class MedLabState(TypedDict):
    # 原始输入
    ocr_text: str
    user_id: str
    
    # 阶段一：KG 抽取特征
    extracted_cuis: List[str]
    kg_constraints: str
    
    # 阶段二：路由与分发信息
    complexity_score: float
    is_complex: bool
    departments: List[str]
    
    # GAT-ReAct 约束机制（新增）
    react_constraint_prompt: str      # ReAct 思考路径约束
    tool_constraints: Dict[str, Any]  # 工具调用约束
    weight_mask: Dict[str, float]     # GAT 权重掩码
    
    # 阶段三：专家会诊上下文
    expert_proposals: Dict[str, str] # { "内科专家": "...", "检验科": "..." }
    debates: List[str]               # 历史对线记录
    
    # 最终输出阶段
    final_report: str
    meta_info: Dict[str, Any]
    constraint_applied: bool          # 是否应用了 GAT-ReAct 约束
