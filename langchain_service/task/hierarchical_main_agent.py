"""
集成主Agent - 将分层多智能体系统与 GAT-ReAct 整合

这是一个新的主Agent实现，它：
1. 使用 GAT 计算各科室的置信度
2. 触发对应科室的轻量级Agent（并联执行）
3. 汇总诊断结果
4. 基于反馈动态更新权重
5. 支持多轮对话
"""

import logging
import asyncio
from typing import Dict, List, Optional, Iterator, Set, Any, Tuple
from datetime import datetime
from collections import defaultdict

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from .lightweight_dept_agent import (
    NephrologyAgent, 
    HematologyAgent, 
    EndocrinologyAgent, 
    PulmonaryAgent, 
    InfectiousAgent,
    LightweightDepartmentAgent
)
from .dept_coordinator import DepartmentAgentCoordinator, ConsensusResult
from utils.weight_updater import get_weight_updater
from knowledge.medical_knowledge import create_knowledge_base
from knowledge.reference_ranges import get_reference_range
from tools import query_user_medical_history, query_medical_knowledge

logger = logging.getLogger(__name__)

_REF_CODE_ALIAS = {
    "Hb": "HB",
    "PO4": "P",
}

_LAB_KEY_ALIAS = {
    "cr": "Cr",
    "creatinine": "Cr",
    "bun": "BUN",
    "egfr": "eGFR",
    "k": "K",
    "po4": "PO4",
    "phosphorus": "PO4",
    "wbc": "WBC",
    "rbc": "RBC",
    "hb": "Hb",
    "hgb": "Hb",
    "hemoglobin": "Hb",
    "plt": "PLT",
    "platelet": "PLT",
    "mcv": "MCV",
    "glu": "GLU",
    "glucose": "GLU",
    "hba1c": "HbA1c",
    "tsh": "TSH",
    "t3": "T3",
    "t4": "T4",
    "crp": "CRP",
    "pct": "PCT",
    "alt": "ALT",
    "ast": "AST",
}


class HierarchicalMedicalAgent:
    """
    分层医学智能体 - 主Agent
    
    架构：
    ┌──────────────────────────────────────────────┐
    │       主Agent（HierarchicalMedicalAgent）      │
    │   - 解析用户查询                              │
    │   - 调用 GAT 计算置信度                      │
    │   - 触发科室轻量级Agent（并联）              │
    │   - 汇总诊断结果                              │
    │   - 决定权重调整                              │
    └──────────────────────────────────────────────┘
              ↓ 并联调用
    ┌──────────┬──────────┬──────────┬──────────┐
    │ 肾内科   │ 血液科   │ 肝胆科   │ ...     │
    │ Agent    │ Agent    │ Agent    │         │
    └──────────┴──────────┴──────────┴──────────┘
    (轻量级，只分析，返回诊断)
    """
    
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.logger = logger
        
        # 初始化知识库
        self.kb = create_knowledge_base()
        
        # 初始化轻量级科室Agent
        self.dept_agents = self._initialize_dept_agents()
        
        # 初始化协调器
        self.coordinator = DepartmentAgentCoordinator(self.dept_agents)
        
        # 获取权重更新器
        self.weight_updater = get_weight_updater()
        
        # 初始化主LLM（用于用户交互和最终综合）
        self.llm = ChatOpenAI(
            model=settings.DASHSCOPE_MODEL,
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.DASHSCOPE_BASE_URL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
            streaming=True,
        )
        
        # 对话历史
        self.conversation_history = []
        
        # 会话状态
        self.session_state = {
            "current_round": 0,
            "analysis_results": [],
            "weight_history": [],
        }
        self.patient_profile: Dict[str, Any] = {}
        self.clinical_prior: str = ""
    
    def _initialize_dept_agents(self) -> Dict[str, LightweightDepartmentAgent]:
        """初始化所有科室Agent - 启用LLM（5个科室）"""
        return {
            "肾内科": NephrologyAgent(use_llm=True),          # ✅ 使用LLM
            "血液科": HematologyAgent(use_llm=True),          # ✅ 使用LLM
            "内分泌科": EndocrinologyAgent(use_llm=True),      # ✅ 使用LLM
            "呼吸科": PulmonaryAgent(use_llm=True),           # ✅ 使用LLM
            "感染科": InfectiousAgent(use_llm=True),          # ✅ 使用LLM
        }
    
    def _compute_gat_confidence(self, lab_results: Dict[str, float]) -> Dict[str, float]:
        """
        使用 GAT 计算各科室的置信度
        
        这里使用简化的启发式规则。在实际应用中，应该使用完整的 GAT 模型。
        
        Returns:
            {"肾内科": 0.7, "血液科": 0.6, ...}
        """
        # 初始化所有科室的置信度
        current_weights = self.weight_updater.get_weights()
        confidence_scores = {}
        
        # 简单规则：基于指标计算初始置信度
        indicator_deps = {
            "Cr": ("肾内科", 0.9),
            "BUN": ("肾内科", 0.85),
            "eGFR": ("肾内科", 0.9),
            "K": ("肾内科", 0.8),
            "WBC": ("血液科", 0.9),
            "RBC": ("血液科", 0.85),
            "Hb": ("血液科", 0.9),
            "PLT": ("血液科", 0.9),
            "ALT": ("肝胆科", 0.9),
            "AST": ("肝胆科", 0.85),
            "GLU": ("内分泌科", 0.9),
            "HbA1c": ("内分泌科", 0.85),
        }
        
        def _is_abnormal(indicator: str, value: float) -> bool:
            code = _REF_CODE_ALIAS.get(indicator, indicator)
            ref = get_reference_range(code)
            if not ref:
                return False
            range_candidates = [
                ref.get("normal"),
                ref.get("fasting"),
                ref.get("adult"),
                ref.get("male"),
                ref.get("female"),
                ref.get("optimal"),
                ref.get("postprandial"),
            ]
            for rr in range_candidates:
                if not isinstance(rr, dict):
                    continue
                low = rr.get("min")
                high = rr.get("max")
                if low is not None and value < low:
                    return True
                if high is not None and value > high:
                    return True
            return False

        # 计算各科室的置信度
        for dept in self.dept_agents.keys():
            dept_confidence = 0.0
            dept_indicator_count = 0
            
            for indicator, (dep, rel) in indicator_deps.items():
                if dep == dept and indicator in lab_results and _is_abnormal(indicator, float(lab_results[indicator])):
                    dept_confidence += rel
                    dept_indicator_count += 1
            
            if dept_indicator_count > 0:
                # 平均置信度 × 权重影响
                avg_confidence = dept_confidence / dept_indicator_count
                weight_factor = current_weights.get(dept, 0.6)
                # 权重因子在 [0.8, 1.2] 范围内调整置信度
                adjusted_confidence = avg_confidence * (0.8 + weight_factor * 0.4 / 2.0)
            else:
                # 无相关指标的科室，使用权重作为置信度
                adjusted_confidence = current_weights.get(dept, 0.5)
            
            confidence_scores[dept] = min(1.0, adjusted_confidence)
        
        self.logger.info(f"【GAT置信度计算】{confidence_scores}")
        
        return confidence_scores

    def _build_task_assignments(
        self,
        lab_results: Dict[str, float],
        gat_confidence: Dict[str, float],
        round_no: int,
    ) -> Dict[str, Dict]:
        """构建主Agent下发给各科室的任务分配字段。"""
        assignments: Dict[str, Dict] = {}
        for dept, agent in self.dept_agents.items():
            focus_indicators = [
                ind
                for ind in getattr(agent, "key_indicators", [])
                if ind in lab_results and getattr(agent, "_is_abnormal")(ind, float(lab_results[ind]))
            ]
            assignments[dept] = {
                "round": round_no,
                "task_goal": "围绕该患者最可能患什么病进行专科判断，并给出需要排除的鉴别诊断",
                "department": dept,
                "focus_indicators": focus_indicators,
                "gate_confidence": round(gat_confidence.get(dept, 0.5), 4),
                "need_user_history": True,
                "patient_profile": self.patient_profile,
                "clinical_prior": self.clinical_prior,
                "required_output": [
                    "primary_diagnosis",
                    "confidence",
                    "clinical_interpretation",
                    "differential_diagnoses",
                    "recommended_tests",
                ],
            }
        return assignments

    def _normalize_lab_results(self, lab_results: Dict[str, float]) -> Dict[str, float]:
        """统一主Agent使用的检验指标命名，避免主循环与科室循环看到的数据不一致。"""
        normalized: Dict[str, float] = {}
        for raw_key, raw_value in (lab_results or {}).items():
            key = str(raw_key).strip()
            mapped = _LAB_KEY_ALIAS.get(key.lower(), key)
            normalized[mapped] = raw_value
        return normalized

    def _is_low_evidence_response(self, resp: Any) -> bool:
        """识别“证据不足/异常兜底”响应，避免其污染冲突与共识。"""
        diag = str(getattr(getattr(resp, "primary_diagnosis", None), "diagnosis", "") or "")
        conf = float(getattr(getattr(resp, "primary_diagnosis", None), "confidence", 0.0) or 0.0)
        handoff = getattr(resp, "handoff_to_main", {}) or {}
        hit_count = len(handoff.get("hit_indicators", []) or [])

        weak_diag_keywords = ["证据不足", "分析异常", "未确定"]
        if any(k in diag for k in weak_diag_keywords):
            return True
        if conf <= 0.4 and hit_count == 0:
            return True
        return False

    def _weighted_consensus(self, responses: Dict[str, Any], conflict_level) -> ConsensusResult:
        """病史一致性 + 指标命中 + 科室权重 的加权共识。"""
        history_text = ""
        try:
            history_text = query_user_medical_history(self.user_id) or ""
        except Exception as exc:
            self.logger.warning("病史查询失败（共识降级）: %s", exc)

        current_weights = self.weight_updater.get_weights()
        diagnosis_scores = defaultdict(float)
        diagnosis_supporters = defaultdict(list)

        def _history_match_bonus(diag: str, history: str) -> float:
            d = (diag or "").lower()
            h = (history or "").lower()
            if not d or not h:
                return 0.0
            pairs = [
                (["肾", "ckd", "kidney"], ["肾", "ckd", "kidney"]),
                (["贫血", "anemia"], ["贫血", "anemia"]),
                (["糖", "糖尿", "diabetes"], ["糖", "糖尿", "diabetes"]),
                (["肝", "肝炎", "hepat"], ["肝", "肝炎", "hepat"]),
                (["感染", "infection"], ["感染", "infection"]),
            ]
            for diag_keys, hist_keys in pairs:
                if any(k in d for k in diag_keys) and any(k in h for k in hist_keys):
                    return 0.1
            return 0.0

        def _prior_match_bonus(diag: str, prior: str) -> float:
            d = (diag or "").lower()
            p = (prior or "").lower()
            if not d or not p:
                return 0.0
            rules = [
                (["肺炎", "感染", "infection", "bronch"], ["肺炎", "感染", "支气管"]),
                (["贫血", "anemia"], ["贫血", "anemia"]),
                (["肾", "ckd", "kidney"], ["肾", "ckd", "kidney"]),
            ]
            for diag_keys, prior_keys in rules:
                if any(k in d for k in diag_keys) and any(k in p for k in prior_keys):
                    return 0.12
            return 0.0

        def _diag_matches_prior(diag: str, prior: str) -> bool:
            return _prior_match_bonus(diag, prior) > 0

        effective_responses = {
            dept: resp for dept, resp in responses.items() if not self._is_low_evidence_response(resp)
        }
        if not effective_responses:
            # 全部低证据时降级到原集合，避免空集导致异常
            effective_responses = responses

        prior_virtual_diag = ""
        prior_virtual_score = 0.0
        if len(effective_responses) == 1 and self.clinical_prior:
            only_dept, only_resp = next(iter(effective_responses.items()))
            only_diag = str(getattr(getattr(only_resp, "primary_diagnosis", None), "diagnosis", "") or "")
            if not _diag_matches_prior(only_diag, self.clinical_prior):
                self.logger.warning(
                    "[REASONING][主Agent] 单科高证据与临床先验不一致，触发防过拟合降权 | dept=%s diag=%s prior=%s",
                    only_dept,
                    only_diag,
                    self.clinical_prior,
                )
                prior_virtual_diag = f"临床先验提示：{self.clinical_prior}（待实验室证实）"
                prior_virtual_score = 0.32

        for dept, resp in effective_responses.items():
            diag = resp.primary_diagnosis.diagnosis
            base_conf = float(resp.primary_diagnosis.confidence)
            handoff = getattr(resp, "handoff_to_main", {}) or {}
            hit_count = len(handoff.get("hit_indicators", []) or [])
            history_bonus = _history_match_bonus(diag, history_text)
            prior_bonus = _prior_match_bonus(diag, self.clinical_prior)
            hit_bonus = min(hit_count * 0.02, 0.2)
            dept_weight = float(current_weights.get(dept, 0.5))

            weighted_score = (base_conf + history_bonus + prior_bonus + hit_bonus) * max(dept_weight, 0.1)
            if prior_virtual_diag and prior_virtual_score > 0:
                weighted_score *= 0.5

            diagnosis_scores[diag] += weighted_score
            diagnosis_supporters[diag].append(dept)

            self.logger.info(
                "[REASONING][主Agent] 共识打分 | 科室=%s 诊断=%s base=%.2f hit=%d bonus(history=%.2f,prior=%.2f,hit=%.2f) weight=%.3f score=%.3f",
                dept,
                diag,
                base_conf,
                hit_count,
                history_bonus,
                prior_bonus,
                hit_bonus,
                dept_weight,
                weighted_score,
            )

        if prior_virtual_diag and prior_virtual_score > 0:
            diagnosis_scores[prior_virtual_diag] += prior_virtual_score
            diagnosis_supporters[prior_virtual_diag].append("临床先验")
            self.logger.info(
                "[REASONING][主Agent] 先验保护项加入共识池 | diag=%s score=%.3f",
                prior_virtual_diag,
                prior_virtual_score,
            )

        best_diag, best_score = max(diagnosis_scores.items(), key=lambda x: x[1])
        supporting_depts = diagnosis_supporters.get(best_diag, [])
        conflicting_depts = [
            d for d, r in effective_responses.items() if r.primary_diagnosis.diagnosis != best_diag
        ]

        denom = max(sum(diagnosis_scores.values()), 1e-6)
        confidence = min(best_score / denom + 0.4, 0.99)
        if best_diag == prior_virtual_diag:
            confidence = min(confidence, 0.78)
        actions = [
            f"主诊断：{best_diag} (加权共识)",
            f"支持科室：{', '.join(supporting_depts) if supporting_depts else '无'}",
        ]
        if conflicting_depts:
            actions.append(f"冲突科室：{', '.join(conflicting_depts)}")

        if conflict_level.value in {"high", "medium"} and conflicting_depts:
            actions.extend(self._resolve_conflict(best_diag, conflicting_depts))

        return ConsensusResult(
            primary_diagnosis=best_diag,
            confidence=confidence,
            supporting_depts=supporting_depts,
            conflicting_depts=conflicting_depts,
            recommended_actions=actions,
        )

    def _resolve_conflict(self, primary_diag: str, conflicting_depts: List[str]) -> List[str]:
        """冲突时给出补充提问和检查建议。"""
        suggestions = [
            f"当前主诊断与{', '.join(conflicting_depts)}存在冲突，建议先按权重较高科室结论执行。",
            "建议补充检查：尿常规、肾脏B超、肝功能全套（ALT/AST/TBIL/DBIL）。",
            "建议追问用户：是否有肝病史、近期是否服用潜在伤肝药物。",
        ]
        return suggestions

    def _is_abnormal_indicator(self, indicator: str, value: float) -> bool:
        """判断化验指标是否异常，用于主Agent状态更新。"""
        age_years = float((self.patient_profile or {}).get("age_years", -1))
        is_pediatric = bool((self.patient_profile or {}).get("is_pediatric")) or (0 <= age_years < 14)

        if is_pediatric:
            pediatric_ranges = {
                "Cr": (15.0, 40.0),
                "TBIL": (0.0, 20.0),
                "DBIL": (0.0, 8.0),
                "HB": (95.0, 145.0),
                "Hb": (95.0, 145.0),
            }
            pr = pediatric_ranges.get(indicator)
            if pr:
                low, high = pr
                return value < low or value > high

        code = _REF_CODE_ALIAS.get(indicator, indicator)
        ref = get_reference_range(code)
        if not ref:
            return False

        range_candidates = [
            ref.get("normal"),
            ref.get("fasting"),
            ref.get("adult"),
            ref.get("male"),
            ref.get("female"),
            ref.get("optimal"),
            ref.get("postprandial"),
        ]
        for rr in range_candidates:
            if not isinstance(rr, dict):
                continue
            low = rr.get("min")
            high = rr.get("max")
            if low is not None and value < low:
                return True
            if high is not None and value > high:
                return True
        return False

    def _detect_data_quality_issues(self, lab_results: Dict[str, float]) -> List[str]:
        """识别高风险OCR误识别，作为ReAct主动纠错触发条件。"""
        issues: List[str] = []
        hb = lab_results.get("Hb")
        if hb is not None and float(hb) > 250:
            issues.append(f"Hb={hb} 超出生理合理区间，疑似 OCR 误配（如 HBDH->Hb）")

        cr = lab_results.get("Cr")
        age_years = float((self.patient_profile or {}).get("age_years", -1))
        is_pediatric = bool((self.patient_profile or {}).get("is_pediatric")) or (0 <= age_years < 14)
        if cr is not None and is_pediatric and float(cr) <= 30:
            issues.append(f"儿科患者 Cr={cr} 可能属于正常儿童范围，请勿按成人低值异常解释")

        return issues

    def _sanitize_lab_results_for_reasoning(
        self,
        lab_results: Dict[str, float],
        data_quality_issues: List[str],
    ) -> Tuple[Dict[str, float], List[str]]:
        """对高风险异常值做隔离，避免错误数据进入后续共识与选科。"""
        sanitized = dict(lab_results or {})
        quarantined: List[str] = []
        issues_text = " | ".join(data_quality_issues or [])

        if "Hb=" in issues_text and "Hb" in sanitized:
            sanitized.pop("Hb", None)
            quarantined.append("Hb")

        age_years = float((self.patient_profile or {}).get("age_years", -1))
        is_pediatric = bool((self.patient_profile or {}).get("is_pediatric")) or (0 <= age_years < 14)
        cr_value = sanitized.get("Cr")
        if is_pediatric and cr_value is not None and float(cr_value) <= 30:
            sanitized.pop("Cr", None)
            quarantined.append("Cr")

        return sanitized, quarantined

    def _prior_department_boost(self, dept: str, prior: str) -> float:
        """把临床先验映射成选科偏置，避免机械按异常值分诊。"""
        p = (prior or "").lower()
        if not p:
            return 0.0

        if any(k in p for k in ["肺炎", "呼吸", "支气管", "咳嗽", "infection", "pneumonia"]):
            if dept in {"呼吸科", "感染科"}:
                return 0.35
            if dept in {"血液科", "肾内科"}:
                return -0.05

        if any(k in p for k in ["肾", "ckd", "kidney"]):
            if dept == "肾内科":
                return 0.25

        if any(k in p for k in ["贫血", "anemia", "血液"]):
            if dept == "血液科":
                return 0.25

        return 0.0

    def _run_early_graph_guidance(self, lab_results: Dict[str, float]) -> Dict[str, Any]:
        """前置运行图推理，直接指导科室动作选择与优先级。"""
        guidance = {
            "key_indicators": [],
            "indicator_weights": {},
            "recommended_agents": [],
            "agent_weights": {},
            "collaboration_notes": [],
        }
        try:
            from graph.graph_inference import get_graph_models

            indicator_gat, expert_gat = get_graph_models()
            graph_nodes = set(getattr(indicator_gat, "graph", {}).nodes()) if getattr(indicator_gat, "graph", None) is not None else set()
            graph_labs = {k: v for k, v in (lab_results or {}).items() if not graph_nodes or k in graph_nodes}
            if not graph_labs:
                self.logger.info("[THOUGHT][主Agent] 图节点无匹配，跳过图推理前置")
                raise ValueError("no matched graph indicators")

            indicator_result = indicator_gat.forward(graph_labs)
            key_indicators = indicator_result.get("key_indicators", [])
            indicator_weights = indicator_result.get("weights", {})
            expert_result = expert_gat.forward(key_indicators, indicator_weights)

            if not key_indicators:
                key_indicators = [
                    k for k, v in graph_labs.items() if self._is_abnormal_indicator(k, float(v))
                ][:5]
                indicator_weights = {k: 0.5 for k in key_indicators}

            guidance.update({
                "key_indicators": key_indicators,
                "indicator_weights": indicator_weights,
                "recommended_agents": expert_result.get("recommended_agents", []) or [],
                "agent_weights": expert_result.get("agent_weights", {}) or {},
                "collaboration_notes": expert_result.get("collaboration_notes", []) or [],
            })
            self.logger.info(
                "[THOUGHT][主Agent] 图推理前置完成 | key=%s | recommend=%s",
                guidance["key_indicators"],
                guidance["recommended_agents"],
            )
        except Exception as exc:
            self.logger.warning("图推理前置失败，降级启发式调度: %s", exc)
            fallback_keys = [
                k for k, v in (lab_results or {}).items() if self._is_abnormal_indicator(k, float(v))
            ][:5]
            guidance["key_indicators"] = fallback_keys
            guidance["indicator_weights"] = {k: 0.5 for k in fallback_keys}
        return guidance

    def _derive_missing_tests(
        self,
        lab_results: Dict[str, float],
        responses: Dict[str, Any],
    ) -> List[str]:
        """根据当前证据缺口给出下一步建议检查。"""
        tests: List[str] = []

        if "WBC" in lab_results and self._is_abnormal_indicator("WBC", float(lab_results["WBC"])):
            if "CRP" not in lab_results:
                tests.append("CRP")
            if "PCT" not in lab_results:
                tests.append("PCT")

        if "Hb" in lab_results and self._is_abnormal_indicator("Hb", float(lab_results["Hb"])):
            if "MCV" in lab_results and float(lab_results["MCV"]) > 100:
                tests.extend(["维生素B12", "叶酸"])
            tests.append("网织红细胞计数")

        if "Cr" in lab_results and self._is_abnormal_indicator("Cr", float(lab_results["Cr"])):
            tests.extend(["尿常规", "尿蛋白/肌酐比值", "肾脏超声"])

        prior = (self.clinical_prior or "").lower()
        if any(k in prior for k in ["肺炎", "支气管", "感染", "pneumonia", "infection"]):
            for t in ["CRP", "PCT", "胸部X线"]:
                if t not in tests:
                    tests.append(t)

        for resp in responses.values():
            for t in getattr(resp, "recommended_tests", []) or []:
                tests.append(t)

        dedup: List[str] = []
        for t in tests:
            if t not in dedup:
                dedup.append(t)
        return dedup[:8]

    def _build_followup_questions(
        self,
        lab_results: Dict[str, float],
        consensus: Optional[ConsensusResult],
    ) -> List[str]:
        """生成下一轮要向用户追问的问题（工具动作）。"""
        qs: List[str] = []

        if "WBC" in lab_results and self._is_abnormal_indicator("WBC", float(lab_results["WBC"])):
            qs.append("近期是否有发热、咳嗽、咽痛或尿频尿痛等感染症状？")

        if "Hb" in lab_results and self._is_abnormal_indicator("Hb", float(lab_results["Hb"])):
            qs.append("是否存在乏力、头晕、黑便或月经过多等失血相关症状？")

        if "Cr" in lab_results and self._is_abnormal_indicator("Cr", float(lab_results["Cr"])):
            qs.append("近期是否出现尿量变化、下肢水肿、夜尿增多或肾病既往史？")

        if consensus and "感染" in (consensus.primary_diagnosis or ""):
            qs.append("近期是否使用过抗生素，是否有寒战或持续高热？")

        prior = (self.clinical_prior or "").lower()
        if any(k in prior for k in ["肺炎", "支气管", "感染", "pneumonia", "infection"]):
            qs.append("是否有发热、咳嗽、咳痰、呼吸急促等呼吸道症状，症状持续了几天？")

        dedup: List[str] = []
        for q in qs:
            if q not in dedup:
                dedup.append(q)
        return dedup[:5]

    def _plan_next_actions(
        self,
        round_no: int,
        lab_results: Dict[str, float],
        gat_confidence: Dict[str, float],
        graph_guidance: Dict[str, Any],
        task_assignments: Dict[str, Dict],
        used_departments: Set[str],
        consensus: Optional[ConsensusResult],
        conflict_report,
        missing_tests: List[str],
        followup_questions: List[str],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """ReAct的 Action 规划：按当前状态动态决定下一步动作。"""
        current_weights = self.weight_updater.get_weights()
        remaining = [d for d in self.dept_agents.keys() if d not in used_departments]
        graph_agent_weights = graph_guidance.get("agent_weights", {}) or {}

        thought = (
            f"第{round_no}轮聚焦异常指标={graph_guidance.get('key_indicators', []) or []}，"
            "结合科室权重/GAT/冲突态势决定下一步动作"
        )

        dept_scores: Dict[str, float] = {}
        for dept in remaining:
            gate = float(gat_confidence.get(dept, 0.0))
            weight = float(current_weights.get(dept, 0.5))
            graph_score = float(graph_agent_weights.get(dept, 0.0))
            focus_count = len(task_assignments.get(dept, {}).get("focus_indicators", []) or [])
            focus_bonus = min(focus_count * 0.06, 0.24)
            prior_boost = self._prior_department_boost(dept, self.clinical_prior)

            conflict_bonus = 0.0
            if consensus and dept in (consensus.conflicting_depts or []):
                conflict_bonus = 0.08

            dept_scores[dept] = gate * 0.45 + weight * 0.30 + graph_score * 0.25 + focus_bonus + conflict_bonus + prior_boost

        sorted_departments = sorted(remaining, key=lambda d: dept_scores.get(d, 0.0), reverse=True)

        if round_no == 1:
            preferred = 3
            reason = "首轮并行验证主要病因与关键鉴别"
        elif conflict_report and conflict_report.level.value in {"high", "medium"}:
            preferred = 3
            reason = "冲突较高，扩大并行会诊范围"
        elif consensus and float(consensus.confidence) < 0.8:
            preferred = 2
            reason = "共识不足，追加并行取证"
        else:
            preferred = 2
            reason = "低冲突增量验证，避免单科室偏置"

        if sorted_departments:
            max_parallel = min(3, len(sorted_departments))
            min_parallel = 2 if len(sorted_departments) >= 2 else 1
            target = max(min_parallel, min(preferred, max_parallel))
            selected_departments = sorted_departments[:target]
        else:
            selected_departments = []

        actions: List[Dict[str, Any]] = []
        if selected_departments:
            actions.append({
                "type": "consult_departments",
                "departments": selected_departments,
                "reason": reason,
                "score_board": {d: round(dept_scores.get(d, 0.0), 4) for d in selected_departments},
            })

        if missing_tests:
            actions.append({
                "type": "request_tests",
                "tests": missing_tests[:5],
                "reason": "当前诊断仍有关键证据缺口",
            })

        if followup_questions:
            actions.append({
                "type": "ask_user",
                "questions": followup_questions[:3],
                "reason": "补充症状与病史以区分鉴别诊断",
            })

        if round_no == 1 or (consensus and float(consensus.confidence) < 0.85):
            keyword = " ".join((graph_guidance.get("key_indicators", []) or [])[:2])
            if not keyword and consensus:
                keyword = consensus.primary_diagnosis
            if keyword:
                actions.append({
                    "type": "retrieve_knowledge",
                    "keyword": keyword,
                    "reason": "主动补充跨科病因学知识用于下一轮推理",
                })

        return thought, actions

    def _execute_non_department_actions(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行 ReAct 中非科室调用动作（提问/补检/检索）。"""
        observation: Dict[str, Any] = {
            "followup_questions": [],
            "recommended_tests": [],
            "knowledge": [],
        }

        for action in actions:
            action_type = action.get("type")
            if action_type == "ask_user":
                qs = action.get("questions", []) or []
                observation["followup_questions"].extend(qs)
                self.logger.info("[ACTION][主Agent] 向用户追问: %s", qs)
            elif action_type == "request_tests":
                tests = action.get("tests", []) or []
                observation["recommended_tests"].extend(tests)
                self.logger.info("[ACTION][主Agent] 建议补充检查: %s", tests)
            elif action_type == "retrieve_knowledge":
                keyword = action.get("keyword", "")
                if keyword:
                    try:
                        snippet = query_medical_knowledge(keyword)
                        observation["knowledge"].append({
                            "keyword": keyword,
                            "summary": (snippet or "")[:300],
                        })
                        self.logger.info("[ACTION][主Agent] 主动检索知识库关键词: %s", keyword)
                    except Exception as exc:
                        self.logger.warning("知识检索动作失败: %s", exc)

        # 去重
        observation["followup_questions"] = list(dict.fromkeys(observation["followup_questions"]))
        observation["recommended_tests"] = list(dict.fromkeys(observation["recommended_tests"]))
        return observation

    def _should_early_stop(
        self,
        round_no: int,
        max_rounds: int,
        consensus: Optional[ConsensusResult],
        conflict_report,
        missing_tests: List[str],
        followup_questions: List[str],
        remaining_departments: List[str],
    ) -> Tuple[bool, str]:
        """更严格的收敛策略，避免第一轮过早停机。"""
        if round_no >= max_rounds:
            return True, "达到最大轮次"

        if not consensus:
            return False, "尚未形成共识"

        unresolved_gap = bool(missing_tests or followup_questions)
        support_count = len(consensus.supporting_depts or [])
        conflict_level = (conflict_report.level.value if conflict_report else "high")

        if round_no < 2:
            if consensus.confidence >= 0.95 and support_count >= 2 and conflict_level in {"none", "low"} and not unresolved_gap:
                return True, "首轮极高共识且无证据缺口"
            return False, "至少完成两轮以验证关键鉴别"

        if consensus.confidence >= 0.9 and support_count >= 2 and conflict_level == "none" and not unresolved_gap:
            return True, "多科一致且证据闭环"

        if not remaining_departments and consensus.confidence >= 0.85 and conflict_level in {"none", "low"} and not unresolved_gap:
            return True, "已无新增科室可调用且共识稳定"

        return False, "继续迭代补证"
    
    async def analyze_lab_results(
        self,
        lab_results: Dict[str, float],
        max_rounds: int = 3,
        patient_profile: Optional[Dict[str, Any]] = None,
        clinical_prior: str = "",
    ) -> Dict:
        """
        分析化验结果 - 完整流程
        
        1. 计算 GAT 置信度
        2. 并联执行科室Agent
        3. 汇总诊断结果
        4. 更新权重
        5. 返回综合结果
        """
        lab_results = self._normalize_lab_results(lab_results)
        self.patient_profile = patient_profile or {}
        self.clinical_prior = clinical_prior or ""
        self.logger.info("[THOUGHT][主Agent] 归一化后检验指标=%s", dict(sorted(lab_results.items())))
        if self.patient_profile:
            self.logger.info("[THOUGHT][主Agent] 患者画像=%s", self.patient_profile)
        if self.clinical_prior:
            self.logger.info("[THOUGHT][主Agent] 临床先验诊断=%s", self.clinical_prior)

        data_quality_issues = self._detect_data_quality_issues(lab_results)
        if data_quality_issues:
            self.logger.warning("[OBSERVATION][主Agent] 数据质量告警: %s", data_quality_issues)

        reasoning_labs, quarantined_indicators = self._sanitize_lab_results_for_reasoning(
            lab_results,
            data_quality_issues,
        )
        if quarantined_indicators:
            self.logger.warning(
                "[ACTION][主Agent] 已隔离高风险指标，避免污染共识: %s",
                quarantined_indicators,
            )
            self.logger.info(
                "[THOUGHT][主Agent] 隔离后用于推理的指标=%s",
                dict(sorted(reasoning_labs.items())),
            )

        all_responses: Dict[str, Any] = {}
        used_departments: Set[str] = set()
        react_rounds: List[Dict] = []
        task_assignments: Dict[str, Dict] = {}
        conflict_report = None
        consensus = None

        graph_guidance = self._run_early_graph_guidance(reasoning_labs)

        for _ in range(max_rounds):
            self.session_state["current_round"] += 1
            round_no = self.session_state["current_round"]

            self.logger.info(f"\n【分析开始】第 {round_no} 轮")

            gat_confidence = self._compute_gat_confidence(reasoning_labs)
            task_assignments = self._build_task_assignments(reasoning_labs, gat_confidence, round_no)

            missing_tests = self._derive_missing_tests(reasoning_labs, all_responses)
            followup_questions = self._build_followup_questions(reasoning_labs, consensus)
            if data_quality_issues:
                followup_questions = list(dict.fromkeys(
                    followup_questions + ["检测到疑似OCR识别异常（如Hb异常偏高），请确认化验单原始数值是否准确。"]
                ))

            thought, actions = self._plan_next_actions(
                round_no=round_no,
                lab_results=reasoning_labs,
                gat_confidence=gat_confidence,
                graph_guidance=graph_guidance,
                task_assignments=task_assignments,
                used_departments=used_departments,
                consensus=consensus,
                conflict_report=conflict_report,
                missing_tests=missing_tests,
                followup_questions=followup_questions,
            )
            self.logger.info("[THOUGHT][主Agent] %s", thought)

            non_dept_obs = self._execute_non_department_actions(actions)

            consult_action = next((a for a in actions if a.get("type") == "consult_departments"), None)
            selected_departments = consult_action.get("departments", []) if consult_action else []
            action_reason = consult_action.get("reason", "无可调用科室") if consult_action else "无可调用科室"

            round_responses: Dict[str, Any] = {}
            if selected_departments:
                self.logger.info(
                    "[ACTION][主Agent] 本轮调用科室=%s | 原因=%s | 分数=%s",
                    selected_departments,
                    action_reason,
                    consult_action.get("score_board", {}),
                )
                round_responses, conflict_report = await self.coordinator.analyze_in_parallel(
                    reasoning_labs,
                    gat_confidence_scores=gat_confidence,
                    user_id=self.user_id,
                    context={
                        "need_user_history": True,
                        "round": round_no,
                        "main_goal": "判断患者最可能患病并形成可解释结论",
                        "reasoning_focus": "疾病收敛 + 鉴别排除",
                        "task_assignments": task_assignments,
                        "peer_handoffs": {
                            dept: resp.handoff_to_main if hasattr(resp, "handoff_to_main") else {}
                            for dept, resp in all_responses.items()
                        },
                    },
                    selected_departments=selected_departments,
                )
                all_responses.update(round_responses)
                used_departments.update(selected_departments)
                self.logger.info(
                    f"[OBSERVATION][主Agent] 收到本轮科室回传数量={len(round_responses)} | "
                    f"累计回传={len(all_responses)} | 冲突级别={conflict_report.level.value}"
                )

            if not conflict_report:
                conflict_report = self.coordinator._detect_conflicts(all_responses)

            if all_responses:
                consensus = self._weighted_consensus(all_responses, conflict_report.level)
                self.logger.info(
                    f"[REASONING][主Agent] 共识推理: 主诊断={consensus.primary_diagnosis}, "
                    f"置信度={consensus.confidence:.2f}, 支持科室={consensus.supporting_depts}, "
                    f"冲突科室={consensus.conflicting_depts}"
                )

                weight_updates = self.coordinator.apply_feedback_and_update_weights(
                    round_responses or all_responses,
                    consensus,
                    conflict_report.level,
                )
                self.logger.info(f"[REASONING][主Agent] 权重迭代结果: {weight_updates}")
            else:
                consensus = None

            round_observation = {
                "department_feedback_count": len(round_responses),
                "conflict_level": conflict_report.level.value if conflict_report else "unknown",
                "followup_questions": non_dept_obs.get("followup_questions", []),
                "recommended_tests": non_dept_obs.get("recommended_tests", []),
                "knowledge_snippets": non_dept_obs.get("knowledge", []),
            }

            react_rounds.append({
                "round": round_no,
                "thought": thought,
                "actions": actions,
                "selected_departments": selected_departments,
                "action_reason": action_reason,
                "observation": round_observation,
                "consensus": {
                    "primary_diagnosis": consensus.primary_diagnosis if consensus else "未确定",
                    "confidence": float(consensus.confidence) if consensus else 0.0,
                    "conflict_level": conflict_report.level.value if conflict_report else "unknown",
                },
            })

            remaining_departments = [d for d in self.dept_agents.keys() if d not in used_departments]
            stop, stop_reason = self._should_early_stop(
                round_no=round_no,
                max_rounds=max_rounds,
                consensus=consensus,
                conflict_report=conflict_report,
                missing_tests=missing_tests,
                followup_questions=followup_questions,
                remaining_departments=remaining_departments,
            )
            self.logger.info("[REASONING][主Agent] 收敛判定=%s | 原因=%s", stop, stop_reason)
            if stop:
                break

        if not all_responses:
            raise RuntimeError("未获得任何科室分析结果")

        analysis_summary = self.coordinator.summarize_analysis(
            all_responses,
            consensus,
            conflict_report,
        )
        analysis_summary["task_assignments"] = task_assignments
        analysis_summary["dept_handoffs"] = {
            dept: resp.handoff_to_main if hasattr(resp, "handoff_to_main") else {}
            for dept, resp in all_responses.items()
        }
        analysis_summary["react_rounds"] = react_rounds
        analysis_summary["graph_guidance"] = graph_guidance
        analysis_summary["patient_profile"] = self.patient_profile
        analysis_summary["clinical_prior"] = self.clinical_prior
        analysis_summary["data_quality_issues"] = data_quality_issues
        analysis_summary["quarantined_indicators"] = quarantined_indicators
        analysis_summary["reasoning_labs"] = reasoning_labs

        self.session_state["analysis_results"].append(analysis_summary)
        self.logger.info(f"【分析完成】诊断：{consensus.primary_diagnosis}")
        return analysis_summary
    
    def stream_final_diagnosis(self, analysis_result: Dict) -> Iterator[str]:
        """
        流式输出最终诊断报告
        
        Yields:
            诊断报告的各个片段
        """
        # 构建系统提示
        system_prompt = """你是一个资深医学顾问，负责根据各个科室的诊断意见生成最终的综合诊断报告。

要求：
1. 整合多个科室的诊断结果
2. 解释诊断的医学依据
3. 提出进一步的检查建议
4. 使用专业但易理解的语言"""
        
        # 构建用户提示
        user_content = f"""
请基于以下分析结果生成最终诊断报告：

【主诊断】{analysis_result['primary_diagnosis']}
【置信度】{analysis_result['consensus_confidence']:.1%}
【支持科室】{', '.join(analysis_result['supporting_departments'])}
【冲突级别】{analysis_result['conflict_level']}

【来自各科室的分析】：
"""
        
        for dept, dept_resp in analysis_result["dept_responses"].items():
            user_content += f"\n{dept}:\n"
            user_content += f"  诊断: {dept_resp['primary_diagnosis']['diagnosis']}\n"
            user_content += f"  置信度: {dept_resp['primary_diagnosis']['confidence']:.1%}\n"
            user_content += f"  证据: {dept_resp['primary_diagnosis']['clinical_evidence']}\n"
        
        # 调用 LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        
        try:
            # 流式响应
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            self.logger.error(f"LLM 调用异常: {e}")
            yield f"\n【诊断异常】无法生成最终诊断，请手动查阅科室意见。"
    
    def get_session_summary(self) -> Dict:
        """获取会话总结"""
        return {
            "user_id": self.user_id,
            "session_start": datetime.now().isoformat(),
            "total_rounds": self.session_state["current_round"],
            "analysis_count": len(self.session_state["analysis_results"]),
            "final_weights": self.weight_updater.get_weights(),
            "weight_statistics": self.weight_updater.get_weight_statistics(),
            "update_history": self.weight_updater.get_update_history(limit=20),
        }


async def demo_hierarchical_agent():
    """演示分层Agent的使用 - 使用LLM"""
    
    print("=" * 70)
    print("【分层医学智能体 - 主Agent演示】使用LLM版本")
    print("=" * 70)
    
    # 初始化主Agent
    agent = HierarchicalMedicalAgent(user_id="test-user-123")
    
    # 模拟化验数据
    lab_results = {
        "Cr": 150,
        "BUN": 28,
        "eGFR": 40,
        "K": 5.2,
        "WBC": 6.5,
        "RBC": 4.0,
        "Hb": 95,
        "PLT": 180,
    }
    
    # 执行分析
    print("\n【执行分析】")
    analysis_result = await agent.analyze_lab_results(lab_results)
    
    # 流式输出诊断
    print("\n【最终诊断】（流式输出）")
    print("-" * 70)
    for chunk in agent.stream_final_diagnosis(analysis_result):
        print(chunk, end="", flush=True)
    print("\n" + "-" * 70)
    
    # 显示会话总结
    print("\n【会话总结】")
    summary = agent.get_session_summary()
    print(f"  总轮数: {summary['total_rounds']}")
    print(f"  最终权重: {summary['final_weights']}")
    print(f"  权重统计: {summary['weight_statistics']}")


if __name__ == "__main__":
    asyncio.run(demo_hierarchical_agent())
