"""
多科室并联协调器

负责：
1. 并联执行所有科室Agent
2. 汇总诊断结果
3. 检测诊断冲突
4. 协调权重更新
"""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from .lightweight_dept_agent import LightweightDepartmentAgent
from .dept_agent_response import DepartmentAgentResponse
from utils.weight_updater import WeightUpdater, get_weight_updater

logger = logging.getLogger(__name__)


class ConflictLevel(Enum):
    """诊断冲突级别"""
    NONE = "none"
    LOW = "low"  # 不影响主要治疗方向
    MEDIUM = "medium"  # 需要进一步确认
    HIGH = "high"  # 需要人工干预


@dataclass
class ConflictReport:
    """冲突报告"""
    level: ConflictLevel
    conflicts: List[Dict] = field(default_factory=list)
    # [
    #     {
    #         "dept1": "肾内科",
    #         "dept2": "血液科",
    #         "conflict": "都认为有贫血，但肾内科认为是继发贫血，血液科认为是原发性贫血",
    #         "severity": "medium"
    #     }
    # ]


@dataclass
class ConsensusResult:
    """共识结果"""
    primary_diagnosis: str
    confidence: float
    supporting_depts: List[str]
    conflicting_depts: List[str]
    recommended_actions: List[str]


class DepartmentAgentCoordinator:
    """科室Agent协调器"""
    
    def __init__(self, dept_agents: Dict[str, LightweightDepartmentAgent]):
        """
        Args:
            dept_agents: 科室Agent字典
            {
                "肾内科": NephrologyAgent(),
                "血液科": HematologyAgent(),
                ...
            }
        """
        self.dept_agents = dept_agents
        self.weight_updater = get_weight_updater()
        self.logger = logger
    
    async def analyze_in_parallel(
        self,
        lab_results: Dict[str, float],
        gat_confidence_scores: Optional[Dict[str, float]] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        selected_departments: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, DepartmentAgentResponse], ConflictReport]:
        """
        并联调用所有科室Agent进行分析
        
        Args:
            lab_results: 化验结果
            gat_confidence_scores: 各科室的GAT置信度
                {"肾内科": 0.7, "血液科": 0.6, ...}
                如果为None，使用weight_updater中的权重作为置信度
        
        Returns:
            (科室响应字典, 冲突报告)
        """
        selected = [d for d in (selected_departments or list(self.dept_agents.keys())) if d in self.dept_agents]
        self.logger.info(f"【并联分析】启动 {len(selected)} 个科室Agent")
        
        # 准备参数
        if gat_confidence_scores is None:
            gat_confidence_scores = self.weight_updater.get_weights()

        task_assignments = (context or {}).get("task_assignments", {})
        for dept, assignment in task_assignments.items():
            self.logger.info(f"[ACTION][主Agent->科室] {dept} 任务分配: {assignment}")
        
        # 构建并发任务
        peer_handoffs = (context or {}).get("peer_handoffs", {}) or {}
        tasks = {
            dept: self._run_agent_async(
                self.dept_agents[dept],
                lab_results,
                gat_confidence_scores.get(dept, 0.5),
                user_id=user_id,
                context={
                    **(context or {}),
                    "task_assignments": {
                        dept: task_assignments.get(dept, {})
                    },
                    "peer_handoffs": {
                        k: v for k, v in peer_handoffs.items() if k != dept
                    },
                },
            )
            for dept in selected
        }
        
        # 并联执行
        try:
            responses = await asyncio.gather(*tasks.values())
            dept_responses = dict(zip(tasks.keys(), responses))
        except Exception as e:
            self.logger.error(f"并联分析异常: {e}", exc_info=True)
            dept_responses = {}
        
        # 分析冲突
        conflict_report = self._detect_conflicts(dept_responses)

        for dept, resp in dept_responses.items():
            self.logger.info(
                f"[OBSERVATION][科室->主Agent] {dept} 回传摘要: {resp.handoff_to_main if hasattr(resp, 'handoff_to_main') else {}}"
            )
        
        self.logger.info(
            f"【并联分析完成】"
            f"{len(dept_responses)} 个科室返回结果 | "
            f"冲突级别: {conflict_report.level.value}"
        )
        
        return dept_responses, conflict_report
    
    async def _run_agent_async(
        self,
        agent: LightweightDepartmentAgent,
        lab_results: Dict[str, float],
        gat_confidence: float,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> DepartmentAgentResponse:
        """异步运行单个Agent"""
        # 这里使用 run_in_executor 来避免阻塞
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            agent.analyze,
            lab_results,
            gat_confidence,
            context,
            user_id,
        )
    
    def _detect_conflicts(self, responses: Dict[str, DepartmentAgentResponse]) -> ConflictReport:
        """检测诊断冲突"""
        conflicts = []
        
        dept_list = list(responses.keys())
        
        # 两两比对
        for i, dept1 in enumerate(dept_list):
            for dept2 in dept_list[i + 1:]:
                resp1 = responses[dept1]
                resp2 = responses[dept2]
                
                # 简单的冲突检测：主诊断完全不同且都高置信度
                if resp1.primary_diagnosis.diagnosis != resp2.primary_diagnosis.diagnosis:
                    if (resp1.primary_diagnosis.confidence > 0.7 and
                        resp2.primary_diagnosis.confidence > 0.7):
                        conflicts.append({
                            "dept1": dept1,
                            "dept2": dept2,
                            "diagnosis1": resp1.primary_diagnosis.diagnosis,
                            "diagnosis2": resp2.primary_diagnosis.diagnosis,
                            "confidence1": resp1.primary_diagnosis.confidence,
                            "confidence2": resp2.primary_diagnosis.confidence,
                            "severity": "high",
                        })
        
        # 判断冲突级别
        if not conflicts:
            level = ConflictLevel.NONE
        elif len(conflicts) <= 1:
            level = ConflictLevel.LOW
        elif len(conflicts) <= 2:
            level = ConflictLevel.MEDIUM
        else:
            level = ConflictLevel.HIGH
        
        return ConflictReport(level=level, conflicts=conflicts)
    
    def get_consensus(
        self,
        responses: Dict[str, DepartmentAgentResponse],
        conflict_level: ConflictLevel
    ) -> ConsensusResult:
        """
        生成共识意见
        
        决策逻辑：
        1. 统计各诊断的支持度
        2. 选择支持度最高的作为主诊断
        3. 返回需要采取的行动
        """
        
        # 收集所有诊断及其支持程度
        diagnosis_support: Dict[str, Tuple[float, List[str]]] = {}  # 诊断 -> (平均置信度, [科室])
        
        for dept, resp in responses.items():
            diag = resp.primary_diagnosis.diagnosis
            conf = resp.primary_diagnosis.confidence
            
            if diag not in diagnosis_support:
                diagnosis_support[diag] = (0, [])
            
            avg_conf, depts = diagnosis_support[diag]
            avg_conf = (avg_conf * len(depts) + conf) / (len(depts) + 1)
            depts.append(dept)
            diagnosis_support[diag] = (avg_conf, depts)
        
        # 选择最佳诊断
        best_diagnosis, (best_confidence, supporting_depts) = max(
            diagnosis_support.items(),
            key=lambda x: x[1][0]
        )
        
        # 找出有分歧的科室
        conflicting_depts = [
            dept for dept in responses.keys()
            if responses[dept].primary_diagnosis.diagnosis != best_diagnosis
        ]
        
        # 根据冲突级别生成建议
        recommended_actions = []
        
        if conflict_level == ConflictLevel.NONE:
            recommended_actions.append(f"主诊断：{best_diagnosis} (共识度高)")
            recommended_actions.append("按常规方案治疗")
        elif conflict_level == ConflictLevel.LOW:
            recommended_actions.append(f"主诊断：{best_diagnosis} (共识度中等)")
            recommended_actions.append("需进一步检查确认")
        elif conflict_level == ConflictLevel.MEDIUM:
            recommended_actions.append(f"初步诊断：{best_diagnosis} (共识度有限)")
            recommended_actions.append("建议多学科会诊")
            recommended_actions.append(f"需重点排除：{', '.join(conflicting_depts) if conflicting_depts else '无'}")
        else:  # HIGH
            recommended_actions.append("诊断共识严重分歧")
            recommended_actions.append("需人工医学审查")
            recommended_actions.append("建议完整的诊断流程重启")
        
        return ConsensusResult(
            primary_diagnosis=best_diagnosis,
            confidence=best_confidence,
            supporting_depts=supporting_depts,
            conflicting_depts=conflicting_depts,
            recommended_actions=recommended_actions,
        )
    
    def apply_feedback_and_update_weights(
        self,
        responses: Dict[str, DepartmentAgentResponse],
        consensus: ConsensusResult,
        conflict_level: ConflictLevel
    ) -> Dict[str, float]:
        """
        基于反馈和共识更新权重
        
        这是实现自适应的关键步骤：
        1. 支持主诊断的科室：权重↑
        2. 产生冲突的科室：权重↓
        3. 记录权重调整历史
        """
        
        self.logger.info("【权重更新】开始基于共识反馈的权重调整")
        
        updates = {}
        
        for dept, resp in responses.items():
            is_supporting = dept in consensus.supporting_depts
            is_conflicting = dept in consensus.conflicting_depts
            
            # 计算权重调整
            if is_supporting and resp.primary_diagnosis.confidence > 0.75:
                delta = 0.15  # 支持且高置信度
                reason = "支持主诊断"
            elif is_conflicting:
                delta = -0.10 - (conflict_level.value == "high") * 0.1  # 冲突，严重冲突更大幅度下调
                reason = f"诊断冲突 ({conflict_level.value})"
            else:
                delta = 0  # 既不支持也不冲突，保持不变
                reason = "保持"
            
            # 更新权重
            if delta != 0:
                new_weight = self.weight_updater.update_from_agent_feedback(
                    department=dept,
                    weight_delta=delta,
                    reason=reason
                )
                updates[dept] = new_weight
        
        return updates
    
    def summarize_analysis(
        self,
        responses: Dict[str, DepartmentAgentResponse],
        consensus: ConsensusResult,
        conflict_report: ConflictReport
    ) -> Dict:
        """生成分析总结"""
        
        return {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "primary_diagnosis": consensus.primary_diagnosis,
            "consensus_confidence": consensus.confidence,
            "supporting_departments": consensus.supporting_depts,
            "conflict_level": conflict_report.level.value,
            "conflicts": conflict_report.conflicts,
            "recommendations": consensus.recommended_actions,
            "dept_responses": {
                dept: resp.to_dict()
                for dept, resp in responses.items()
            },
            "weight_updates": self.weight_updater.get_weights(),
        }
