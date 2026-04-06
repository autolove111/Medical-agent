"""
完整的 GAT-ReAct 诊疗链路实现

将三个核心阶段完整连接：
  1. Thought (思考) - GAT 约束指导下的理性分析
  2. Action (行动) - 受工具约束的受控工具调用
  3. Observation (观察) - 收集工具反馈并迭代

完整的 ReAct 循环：
  Thought → Action → Observation → Thought → ... → Conclusion
"""

import logging
import json
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

logger = logging.getLogger(__name__)


class ReActPhase(Enum):
    """ReAct 流程阶段"""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    CONCLUSION = "conclusion"


@dataclass
class ThoughtStep:
    """思考步骤"""
    phase: ReActPhase
    content: str
    reasoning: str  # 推理过程
    constraints_applied: List[str] = None  # 应用的约束列表
    
    def to_dict(self) -> Dict:
        return {
            "phase": self.phase.value,
            "content": self.content,
            "reasoning": self.reasoning,
            "constraints_applied": self.constraints_applied or []
        }


@dataclass
class ActionStep:
    """行动步骤"""
    tool_name: str
    tool_input: Dict[str, Any]
    constraint_priority: int  # 优先级（1 最高，999 最低）
    allowed: bool  # 是否被约束允许
    
    def to_dict(self) -> Dict:
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "priority": self.constraint_priority,
            "allowed": self.allowed
        }


@dataclass
class ObservationResult:
    """观察结果"""
    tool_result: str
    confidence: float  # 结果可信度 [0, 1]
    relevant_to_diagnosis: bool  # 是否与诊断相关
    next_thought: Optional[str] = None  # 建议的下一步思考
    
    def to_dict(self) -> Dict:
        return {
            "result": self.tool_result,
            "confidence": self.confidence,
            "relevant": self.relevant_to_diagnosis,
            "next_thought": self.next_thought
        }


class GATReActDiagnosisEngine:
    """GAT-ReAct 诊疗引擎 - 完整的思维-行动-观察循环"""
    
    def __init__(
        self,
        llm,
        tool_constraints: Dict[str, Any],
        weight_mask: Dict[str, float],
        react_constraint_prompt: str,
        key_indicators: List[str]
    ):
        """
        初始化诊疗引擎
        
        Args:
            llm: 语言模型
            tool_constraints: 工具约束字典
            weight_mask: 部门权重掩码
            react_constraint_prompt: 约束提示词
            key_indicators: 关键指标列表
        """
        self.llm = llm
        self.tool_constraints = tool_constraints
        self.weight_mask = weight_mask
        self.react_constraint_prompt = react_constraint_prompt
        self.key_indicators = key_indicators
        
        # 迭代历史
        self.thought_history: List[ThoughtStep] = []
        self.action_history: List[ActionStep] = []
        self.observation_history: List[ObservationResult] = []
    
    def generate_thought(
        self,
        context: str,
        iteration_number: int = 1,
        previous_observations: Optional[str] = None
    ) -> ThoughtStep:
        """
        第1阶段：生成思考（Thought）
        
        约束：必须遵循 GAT 生成的思考路径约束
        
        Args:
            context: 诊疗上下文
            iteration_number: 迭代次数
            previous_observations: 之前的观察结果总结
        
        Returns:
            ThoughtStep 对象
        """
        logger.info(f"[ReAct Thought #{iteration_number}] 生成诊疗思考...")
        
        # 构建思考提示词
        thought_prompt = self._build_thought_prompt(
            context,
            iteration_number,
            previous_observations
        )
        
        messages = [
            SystemMessage(content=self.react_constraint_prompt),
            HumanMessage(content=thought_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            thought_content = response.content
            
            # 提取约束应用信息
            constraints_applied = self._extract_applied_constraints(thought_content)
            
            thought_step = ThoughtStep(
                phase=ReActPhase.THOUGHT,
                content=thought_content,
                reasoning=self._extract_reasoning(thought_content),
                constraints_applied=constraints_applied
            )
            
            self.thought_history.append(thought_step)
            logger.info(f"✅ 思考完成 (应用约束: {len(constraints_applied)} 条)")
            
            return thought_step
            
        except Exception as e:
            logger.error(f"思考生成失败: {e}")
            raise
    
    def propose_action(self, thought_step: ThoughtStep) -> ActionStep:
        """
        第2阶段：提议行动（Action Proposal）
        
        从思考中提取要采取的行动，并验证是否符合工具约束
        
        Args:
            thought_step: 思考步骤
        
        Returns:
            ActionStep 对象
        """
        logger.info("[ReAct Action Proposal] 分析思考中的行动建议...")
        
        # 从思考中提取工具调用建议
        tool_name, tool_input = self._extract_tool_from_thought(thought_step.content)
        
        if not tool_name:
            logger.warning("无法从思考中提取工具调用")
            return None
        
        # 验证工具是否被约束允许
        allowed, reason = self._validate_tool_call(tool_name)
        priority = self.tool_constraints['tool_priority'].get(tool_name, 999)
        
        action_step = ActionStep(
            tool_name=tool_name,
            tool_input=tool_input,
            constraint_priority=priority,
            allowed=allowed
        )
        
        self.action_history.append(action_step)
        
        if allowed:
            logger.info(
                f"✅ 工具 {tool_name} 已验证 (优先级 {priority})"
            )
        else:
            logger.warning(f"❌ 工具 {tool_name} 被约束禁止: {reason}")
        
        return action_step
    
    def execute_action(
        self,
        action_step: ActionStep,
        tool_callable,  # 实际的工具函数
    ) -> ObservationResult:
        """
        第3阶段：执行行动（Action Execution）
        
        在约束允许的情况下执行工具调用
        
        Args:
            action_step: 行动步骤
            tool_callable: 可调用的工具函数
        
        Returns:
            ObservationResult 对象
        """
        logger.info(f"[ReAct Observation] 执行工具: {action_step.tool_name}")
        
        if not action_step.allowed:
            error_msg = f"工具 {action_step.tool_name} 被约束禁止，无法执行"
            logger.error(f"❌ {error_msg}")
            result = ObservationResult(
                tool_result=error_msg,
                confidence=0.0,
                relevant_to_diagnosis=False
            )
            self.observation_history.append(result)
            return result
        
        try:
            # 调用工具
            tool_result = tool_callable(**action_step.tool_input)
            
            # 评估结果的诊断相关性和可信度
            confidence = self._evaluate_result_confidence(
                action_step.tool_name,
                tool_result
            )
            relevant = self._is_result_relevant(tool_result)
            
            result = ObservationResult(
                tool_result=tool_result,
                confidence=confidence,
                relevant_to_diagnosis=relevant,
                next_thought=self._suggest_next_thought(tool_result)
            )
            
            self.observation_history.append(result)
            logger.info(
                f"✅ 工具执行完成 (可信度: {confidence:.2f}, 相关性: {relevant})"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"工具执行失败: {e}")
            result = ObservationResult(
                tool_result=f"工具执行错误: {str(e)}",
                confidence=0.0,
                relevant_to_diagnosis=False
            )
            self.observation_history.append(result)
            return result
    
    def should_continue_reasoning(
        self,
        iteration_number: int,
        max_iterations: int = 3,
        recent_observations: List[ObservationResult] = None
    ) -> bool:
        """
        判断是否应该继续推理循环
        
        Args:
            iteration_number: 当前迭代次数
            max_iterations: 最大迭代次数
            recent_observations: 最近的观察结果
        
        Returns:
            bool - 是否继续
        """
        # 达到最大迭代次数
        if iteration_number >= max_iterations:
            logger.info(f"已达到最大迭代次数 ({max_iterations})")
            return False
        
        # 检查最近的观察是否充分
        if recent_observations:
            avg_confidence = sum(
                obs.confidence for obs in recent_observations
            ) / len(recent_observations)
            
            if avg_confidence > 0.85:
                logger.info("观察结果信心度足够高，可以结束推理")
                return False
        
        logger.info(f"继续推理循环 (迭代 {iteration_number + 1}/{max_iterations})")
        return True
    
    def generate_conclusion(self, full_context: str) -> str:
        """
        生成最终诊疗结论
        
        Args:
            full_context: 完整的诊疗上下文
        
        Returns:
            str - 最终诊疗意见
        """
        logger.info("[ReAct Conclusion] 综合所有推理生成最终诊疗意见...")
        
        # 构建完整的诊疗记录
        diagnosis_record = self._build_diagnosis_record()
        
        conclusion_prompt = f"""基于以下完整的诊疗推理过程，请给出最终诊疗意见：

【诊疗过程记录】
{diagnosis_record}

【完整上下文】
{full_context}

请综合多次思考、行动、观察的结果，给出专业的诊疗建议。
必须包括：
1. 主要诊断
2. 差分诊断
3. 诊断信心度
4. 诊疗建议
5. 后续检查建议

并提醒：以上建议仅供参考，请以临床医生诊断为准。"""
        
        messages = [
            SystemMessage(content="你是专业的医学诊疗系统，基于完整的推理过程给出结论"),
            HumanMessage(content=conclusion_prompt)
        ]
        
        response = self.llm.invoke(messages)
        conclusion = response.content
        
        logger.info("✅ 最终诊疗意见已生成")
        
        return conclusion
    
    # 辅助方法
    
    def _build_thought_prompt(
        self,
        context: str,
        iteration_number: int,
        previous_observations: Optional[str]
    ) -> str:
        """构建思考提示词"""
        lines = []
        lines.append(f"【诊疗推理第 {iteration_number} 轮】\n")
        lines.append(f"关键指标：{', '.join(self.key_indicators)}\n")
        lines.append(f"【当前诊疗上下文】\n{context}")
        
        if previous_observations:
            lines.append(f"\n【前一轮观察结果】\n{previous_observations}")
        
        lines.append("""
请按以下格式输出你的思考：

Thought: [你的理性分析过程]
Action: [建议调用的工具名称]
ActionInput: [工具的输入参数]

请严格遵循 GAT 生成的约束条件！""")
        
        return "\n".join(lines)
    
    def _validate_tool_call(self, tool_name: str) -> Tuple[bool, str]:
        """验证工具调用是否被约束允许"""
        return (
            tool_name in self.tool_constraints['allowed_tools'],
            f"Tool {tool_name} not in allowed list"
        )
    
    def _extract_tool_from_thought(self, thought_content: str) -> Tuple[Optional[str], Dict]:
        """从思考内容中提取工具建议"""
        # 简化实现：查找 Action: 行
        import re
        
        action_match = re.search(r'Action:\s*(\w+)', thought_content)
        if not action_match:
            return None, {}
        
        tool_name = action_match.group(1)
        
        # 简单的输入提取
        input_match = re.search(r'ActionInput:\s*({.*?}|".*?")', thought_content, re.DOTALL)
        tool_input = {}
        if input_match:
            try:
                tool_input = json.loads(input_match.group(1))
            except:
                pass
        
        return tool_name, tool_input
    
    def _extract_reasoning(self, thought_content: str) -> str:
        """从思考中提取推理过程"""
        import re
        match = re.search(r'Thought:\s*(.+?)(?=Action:|$)', thought_content, re.DOTALL)
        return match.group(1).strip() if match else thought_content[:200]
    
    def _extract_applied_constraints(self, thought_content: str) -> List[str]:
        """提取思考中应用的约束"""
        constraints = []
        if "优先级" in thought_content or "Priority" in thought_content:
            constraints.append("权重优先级约束")
        if "关键指标" in thought_content or "Key Indicators" in thought_content:
            constraints.append("指标关联约束")
        if "允许" in thought_content or "allowed" in thought_content.lower():
            constraints.append("工具集约束")
        return constraints
    
    def _evaluate_result_confidence(self, tool_name: str, result: str) -> float:
        """评估工具结果的可信度"""
        # 简单启发式：关键工具优先级越高，可信度越高
        priority = self.tool_constraints['tool_priority'].get(tool_name, 999)
        base_confidence = 1.0 - (priority / 1000.0)
        return max(0.0, min(1.0, base_confidence + 0.1))
    
    def _is_result_relevant(self, result: str) -> bool:
        """判断结果是否与诊断相关"""
        if not result or len(result) < 10:
            return False
        return True
    
    def _suggest_next_thought(self, tool_result: str) -> str:
        """建议下一步思考"""
        if "错误" in tool_result or "失败" in tool_result:
            return "工具执行失败，尝试替代工具"
        return "结果已获得，继续推理"
    
    def _build_diagnosis_record(self) -> str:
        """构建诊疗推理记录"""
        lines = []
        for i, thought in enumerate(self.thought_history, 1):
            lines.append(f"\n🧠 第 {i} 轮思考：")
            lines.append(f"  推理: {thought.reasoning[:100]}...")
            if i < len(self.action_history):
                action = self.action_history[i-1]
                lines.append(f"📍 行动: {action.tool_name} (优先级 {action.constraint_priority})")
                if i < len(self.observation_history):
                    obs = self.observation_history[i-1]
                    lines.append(f"👁️  观察: {obs.tool_result[:100]}... (信心度 {obs.confidence:.2f})")
        
        return "\n".join(lines)
    
    def export_full_trace(self) -> Dict:
        """导出完整的推理过程追踪"""
        return {
            "thoughts": [t.to_dict() for t in self.thought_history],
            "actions": [a.to_dict() for a in self.action_history],
            "observations": [o.to_dict() for o in self.observation_history],
            "weight_mask": self.weight_mask,
            "tool_constraints": {
                "primary_tools": self.tool_constraints.get('primary_tools', []),
                "allowed_tools_count": len(self.tool_constraints.get('allowed_tools', set())),
                "forbidden_tools_count": len(self.tool_constraints.get('forbidden_tools', set())),
            }
        }
