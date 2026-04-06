"""
GAT-ReAct 协同会诊约束引擎

功能：
  1. 生成权重掩码（Weight Mask）
  2. 动态工具集过滤（Dynamic Tool Set Filtering）
  3. ReAct 思考路径约束（ReAct Thought Path Constraint）
  4. 工具调用优先级编码
"""

import logging
from typing import Dict, List, Set, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class ReactConstraintEngine:
    """ReAct 约束引擎 - 将 GAT 权重转化为 ReAct Agent 的操作约束"""
    
    DEFAULT_ALLOWED_TOOLS = {
        "query_user_medical_history",
        "retrieve_medical_knowledge",
        "query_drug_interactions",
        "consult_specialist",
        "order_diagnostic_test",
    }
    
    def __init__(self):
        """初始化约束引擎"""
        self.tool_family_mapping = self._init_tool_family()
        self.dept_to_tools = self._init_dept_to_tools()
    
    @staticmethod
    def _init_tool_family() -> Dict[str, Set[str]]:
        """
        定义工具家族（Tool Family）
        同一家族的工具在 GAT 权重中有较强的关联性
        
        Returns:
            Dict: {family_name -> Set[tool_names]}
        """
        return {
            "kidney_tools": {
                "check_renal_function",
                "query_glomerular_filtration_rate",
                "assess_proteinuria_level",
            },
            "cardiac_tools": {
                "analyze_heart_rhythm",
                "check_troponin_level",
                "assess_cardiac_dysfunction",
                "order_echocardiogram",
            },
            "hematology_tools": {
                "analyze_blood_cell_counts",
                "check_hemoglobin_level",
                "assess_platelet_aggregation",
            },
            "endocrinology_tools": {
                "check_glucose_level",
                "analyze_hba1c",
                "assess_thyroid_function",
            },
            "gastroenterology_tools": {
                "check_liver_function",
                "analyze_bile_acids",
                "assess_digestive_enzymes",
            },
            "infectious_tools": {
                "check_infection_markers",
                "analyze_inflammatory_response",
                "assess_immunological_status",
            },
        }
    
    @staticmethod
    def _init_dept_to_tools() -> Dict[str, Set[str]]:
        """
        定义科室到工具的映射
        
        Returns:
            Dict: {department_name -> Set[tool_names]}
        """
        return {
            "RenalDepartment": {
                "check_renal_function",
                "query_glomerular_filtration_rate",
                "assess_proteinuria_level",
                "consult_nephrologist",
            },
            "CardiologyDepartment": {
                "analyze_heart_rhythm",
                "check_troponin_level",
                "assess_cardiac_dysfunction",
                "order_echocardiogram",
                "consult_cardiologist",
            },
            "HematologyDepartment": {
                "analyze_blood_cell_counts",
                "check_hemoglobin_level",
                "assess_platelet_aggregation",
                "consult_hematologist",
            },
            "EndocrinologyDepartment": {
                "check_glucose_level",
                "analyze_hba1c",
                "assess_thyroid_function",
                "consult_endocrinologist",
            },
            "GastroenterologyDepartment": {
                "check_liver_function",
                "analyze_bile_acids",
                "assess_digestive_enzymes",
                "consult_gastroenterologist",
            },
            "InfectiousDepartment": {
                "check_infection_markers",
                "analyze_inflammatory_response",
                "assess_immunological_status",
                "consult_infectious_disease_specialist",
            },
        }
    
    def generate_weight_mask(
        self,
        agent_weights: Dict[str, float],
        include_threshold: float = 0.2,
        scale_factor: float = 100.0
    ) -> Dict[str, float]:
        """
        从 GAT Agent 权重生成权重掩码（Weight Mask）
        
        权重掩码用于在 ReAct 的理性（Reasoning）阶段直接指导 Agent
        调用哪些工具以及以什么顺序。
        
        Args:
            agent_weights: {dept_or_agent_name -> weight [0, 1]}
            include_threshold: 权重低于此值的 Agent 将被排除
            scale_factor: 将权重放大以便在提示词中展示
        
        Returns:
            Dict: {dept_or_agent_name -> scaled_weight}
        """
        if not agent_weights:
            logger.warning("Empty agent_weights provided to generate_weight_mask")
            return {}
        
        # 过滤权重
        filtered_weights = {
            name: weight for name, weight in agent_weights.items()
            if weight >= include_threshold
        }
        
        if not filtered_weights:
            logger.warning(f"No agents above threshold {include_threshold}")
            return {}
        
        # 标准化并缩放
        max_weight = max(filtered_weights.values())
        if max_weight == 0:
            max_weight = 1.0
        
        weight_mask = {
            name: (weight / max_weight) * scale_factor
            for name, weight in filtered_weights.items()
        }
        
        logger.info(f"Generated weight mask: {weight_mask}")
        return weight_mask
    
    def generate_tool_constraints(
        self,
        involved_departments: List[str],
        weight_mask: Dict[str, float],
        num_primary_tools: int = 3
    ) -> Dict:
        """
        从 GAT 输出生成工具调用约束
        
        Args:
            involved_departments: 涉及的科室列表
            weight_mask: 权重掩码
            num_primary_tools: 首选工具的数量
        
        Returns:
            Dict: {
                'primary_tools': List[str],        # 优先调用的工具
                'allowed_tools': Set[str],         # 允许调用的全部工具
                'tool_priority': Dict[str, int],   # 工具优先级编号
                'forbidden_tools': Set[str],       # 禁止调用的工具
            }
        """
        all_allowed_tools = set(self.DEFAULT_ALLOWED_TOOLS)
        
        for dept in involved_departments:
            if dept in self.dept_to_tools:
                all_allowed_tools.update(self.dept_to_tools[dept])
        
        # 生成工具优先级
        tool_priority = {}
        priority_counter = 1
        
        # 根据权重排序科室
        sorted_depts = sorted(
            weight_mask.items(),
            key=lambda x: x[1],
            reverse=True
        )[:num_primary_tools]
        
        # 为最高权重的科室的工具设置最高优先级
        primary_tools = []
        for dept, weight in sorted_depts:
            if dept in self.dept_to_tools:
                dept_tools = self.dept_to_tools[dept]
                primary_tools.extend(dept_tools)
                for tool in dept_tools:
                    tool_priority[tool] = priority_counter
                priority_counter += 1
        
        # 其他允许的工具设置较低优先级
        for tool in all_allowed_tools:
            if tool not in tool_priority:
                tool_priority[tool] = 999  # 低优先级
        
        # 禁止调用的工具：所有不在允许集合中的工具
        all_possible_tools = set(self.DEFAULT_ALLOWED_TOOLS)
        for tool_set in self.dept_to_tools.values():
            all_possible_tools.update(tool_set)
        
        forbidden_tools = all_possible_tools - all_allowed_tools
        
        return {
            'primary_tools': primary_tools[:num_primary_tools],
            'allowed_tools': all_allowed_tools,
            'tool_priority': tool_priority,
            'forbidden_tools': forbidden_tools,
        }
    
    def generate_thought_constraint_prompt(
        self,
        key_indicators: List[str],
        weight_mask: Dict[str, float],
        tool_constraints: Dict
    ) -> str:
        """
        生成 ReAct 思考路径约束提示词
        
        这个提示词会被注入到 ReAct Agent 的 system prompt 中，
        强制 Agent 在其"思考"（Thought）阶段遵循这些约束。
        
        Args:
            key_indicators: 关键指标列表
            weight_mask: 权重掩码
            tool_constraints: 工具约束字典
        
        Returns:
            str: 约束提示词
        """
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("[GAT-ReAct 约束指令] - 必须遵循")
        lines.append("=" * 70)
        
        # 指标约束
        lines.append("\n【关键指标检出】")
        for ind in key_indicators[:5]:
            lines.append(f"  ✓ {ind}")
        
        # 权重掩码约束
        lines.append("\n【部门权重掩码】（按优先级排序）")
        sorted_weights = sorted(
            weight_mask.items(),
            key=lambda x: x[1],
            reverse=True
        )
        for i, (dept, weight) in enumerate(sorted_weights[:3], 1):
            lines.append(f"  {i}. {dept}: {weight:.1f}% 优先级")
        
        # 工具调用约束
        lines.append("\n【工具调用优先级】")
        lines.append("  ⭐ 必须优先调用（前 2 个）：")
        for i, tool in enumerate(tool_constraints['primary_tools'][:2], 1):
            lines.append(f"    {i}. {tool}")
        
        lines.append("\n  ✓ 允许调用:")
        allowed = list(tool_constraints['allowed_tools'])[:5]
        for tool in allowed:
            lines.append(f"    • {tool}")
        
        if tool_constraints['forbidden_tools']:
            lines.append("\n  ✗ 禁止调用（会浪费 Token）:")
            for tool in list(tool_constraints['forbidden_tools'])[:3]:
                lines.append(f"    • {tool}")
        
        # 强制路径指令
        lines.append("\n【强制思考路径】")
        lines.append("""  在你的 Thought 中，必须按以下顺序思考：
  
  Step 1: [调用关键指标检查工具]
          → 先调用权重最高部门的诊断工具
  
  Step 2: [收集辅助信息]
          → 然后调用次要部门的检查工具
  
  Step 3: [综合分析]
          → 整合所有工具返回结果，给出诊断建议
  
  ⚠️  禁止：调用与关键指标无关的工具""")
        
        lines.append("\n" + "=" * 70 + "\n")
        
        return "\n".join(lines)
    
    def generate_tool_function_prompt(
        self,
        tool_constraints: Dict
    ) -> str:
        """
        生成工具使用说明（可选）
        
        用于生成工具的使用说明文本
        """
        lines = []
        lines.append("\n## 可用工具列表")
        
        for tool in sorted(tool_constraints['allowed_tools']):
            priority = tool_constraints['tool_priority'].get(tool, 999)
            if priority <= 5:
                icon = "🔥"  # 高优先级
            elif priority <= 20:
                icon = "✓"   # 中优先级
            else:
                icon = "•"   # 低优先级
            
            lines.append(f"{icon} {tool} (优先级: {priority})")
        
        return "\n".join(lines)
    
    def validate_tool_call(
        self,
        tool_name: str,
        tool_constraints: Dict
    ) -> Tuple[bool, str]:
        """
        验证工具调用是否符合约束
        
        Args:
            tool_name: 工具名称
            tool_constraints: 工具约束字典
        
        Returns:
            Tuple: (是否允许, 原因说明)
        """
        if tool_name in tool_constraints['forbidden_tools']:
            return False, f"❌ 工具 {tool_name} 不相关，已被禁用"
        
        if tool_name not in tool_constraints['allowed_tools']:
            return False, f"❌ 工具 {tool_name} 不在允许列表中"
        
        priority = tool_constraints['tool_priority'].get(tool_name, 999)
        if priority <= 5:
            return True, f"✔️ 工具 {tool_name} 是关键工具（优先级 {priority}）"
        else:
            return True, f"✓ 工具 {tool_name} 可调用（优先级 {priority}）"


# 全局实例
_constraint_engine = None


def get_constraint_engine() -> ReactConstraintEngine:
    """获取全局约束引擎实例"""
    global _constraint_engine
    if _constraint_engine is None:
        _constraint_engine = ReactConstraintEngine()
    return _constraint_engine
