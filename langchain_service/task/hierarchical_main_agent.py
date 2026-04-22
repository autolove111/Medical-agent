
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
import re
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
from knowledge.tools import query_user_medical_history, query_medical_knowledge, query_user_age_profile

logger = logging.getLogger(__name__)

_REF_CODE_ALIAS = {
    "Hb": "HB",
    "PO4": "P",
}

_LAB_KEY_ALIAS = {
    # ========== 血细胞计数 ==========
    "wbc": "WBC",
    "rbc": "RBC",
    "hb": "Hb",
    "hgb": "Hb",
    "hemoglobin": "Hb",
    "hematocrit": "HCT",
    "hct": "HCT",
    "mcv": "MCV",
    "mch": "MCH",
    "mchc": "MCHC",
    "plt": "PLT",
    "platelet": "PLT",
    # ========== 白细胞分类 ==========
    "ne": "NE",
    "ly": "LY",
    "mo": "MO",
    "eo": "EO",
    "ba": "BA",
    # ========== 红细胞分类 ==========
    "nrbc": "NRBC",
    "rdw": "RDW",
    # ========== 血小板相关 ==========
    "mpv": "MPV",
    "pct": "PCT",
    "pdw": "PDW",
    # ========== 生化指标：代谢 ==========
    "glu": "GLU",
    "glucose": "GLU",
    "bun": "BUN",
    "cr": "Cr",
    "creatinine": "Cr",
    "uric_acid": "UA",
    "ua": "UA",
    # ========== 生化指标：肝功能 ==========
    "alt": "ALT",
    "ast": "AST",
    "alp": "ALP",
    "ggt": "GGT",
    "total_bilirubin": "TBIL",
    "direct_bilirubin": "DBIL",
    "tbil": "TBIL",
    "dbil": "DBIL",
    # ========== 生化指标：电解质 ==========
    "sodium": "Na",
    "na": "Na",
    "potassium": "K",
    "k": "K",
    "chloride": "Cl",
    "cl": "Cl",
    "calcium": "Ca",
    "ca": "Ca",
    "phosphorus": "P",
    "po4": "PO4",
    "p": "PO4",
    "magnesium": "Mg",
    "mg": "Mg",
    # ========== 生化指标：脂质 ==========
    "cholesterol": "CHO",
    "triglyceride": "TG",
    # ========== 蛋白质代谢 ==========
    "total_protein": "TP",
    "albumin": "ALB",
    "globulin": "GLO",
    "a_g_ratio": "A/G",
    # ========== 胆汁和肝脏 ==========
    "total_bile_acid": "TBA",
    "cholinesterase": "CHE",
    # ========== 心肌酶 ==========
    "creatine_kinase": "CK",
    "ck": "CK",
    "ldh": "LDH",
    "a_hbd": "α-HBD",
    # ========== 肾功能扩展 ==========
    "urea": "UREA",
    "cystatin_c": "CysC",
    # ========== 酸碱平衡 ==========
    "co2": "CO2",
    "ph": "pH",
    "pco2": "pCO2",
    "po2": "pO2",
    "hco3": "HCO3",
    "o2sat": "O2Sat",
    # ========== 感染分类（百分比） ==========
    "neut%": "NEUT%",
    "lymph%": "LYMPH%",
    "neut": "NEUT%",
    "lymph": "LYMPH%",
    # ========== 原有保留兼容项 ==========
    "egfr": "eGFR",
    "hba1c": "HbA1c",
    "tsh": "TSH",
    "t3": "T3",
    "t4": "T4",
    "crp": "CRP",
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

    def _resolve_age_group(self) -> str:
        """统一年龄分层，作为参考范围选择依据。"""
        age_years = -1.0
        try:
            profile_age = (self.patient_profile or {}).get("age_years")
            if profile_age is not None:
                age_years = float(profile_age)
            else:
                age_profile = query_user_age_profile(self.user_id) or {}
                if age_profile.get("age_years") is not None:
                    age_years = float(age_profile.get("age_years"))
        except Exception as exc:
            self.logger.warning("年龄画像查询失败，按 19-64 默认分层处理: %s", exc)

        if 0 <= age_years <= 14:
            return "0_14"
        if 15 <= age_years <= 18:
            return "15_18"
        if age_years >= 65:
            return "65_plus"
        return "19_64"

    def _reference_bounds_by_age_group(
        self,
        indicator: str,
        age_group: str,
    ) -> tuple[Optional[float], Optional[float]]:
        code = _REF_CODE_ALIAS.get(indicator, indicator)
        ref = get_reference_range(code)
        if not ref:
            return None, None

        gender_raw = str((self.patient_profile or {}).get("gender", "") or "").strip().lower()
        if ("女" in gender_raw) or gender_raw.startswith("f"):
            gender_candidates = [ref.get("female"), ref.get("male")]
        elif ("男" in gender_raw) or gender_raw.startswith("m"):
            gender_candidates = [ref.get("male"), ref.get("female")]
        else:
            gender_candidates = [ref.get("male"), ref.get("female")]

        match age_group:
            case "0_14":
                range_candidates = [
                    ref.get("pediatric"),
                    ref.get("child"),
                    ref.get("infant"),
                    ref.get("adolescent"),
                    *gender_candidates,
                    ref.get("adult"),
                    ref.get("normal"),
                ]
            case "15_18":
                range_candidates = [
                    ref.get("adolescent"),
                    ref.get("teen"),
                    ref.get("pediatric"),
                    *gender_candidates,
                    ref.get("adult"),
                    ref.get("normal"),
                ]
            case "19_64":
                range_candidates = [
                    *gender_candidates,
                    ref.get("fasting"),
                    ref.get("optimal"),
                    ref.get("postprandial"),
                    ref.get("adult"),
                    ref.get("normal"),
                ]
            case "65_plus":
                range_candidates = [
                    ref.get("elderly"),
                    ref.get("geriatric"),
                    ref.get("senior"),
                    *gender_candidates,
                    ref.get("adult"),
                    ref.get("normal"),
                ]
            case _:
                range_candidates = [
                    *gender_candidates,
                    ref.get("adult"),
                    ref.get("normal"),
                ]

        for rr in range_candidates:
            if not isinstance(rr, dict):
                continue
            low = rr.get("min")
            high = rr.get("max")
            if low is not None or high is not None:
                return low, high
        return None, None

    def _compute_abnormal_bundle(self, lab_results: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
        """主Agent统一计算异常包，供各科室复用，避免重复判定。"""
        abnormal_bundle: Dict[str, Dict[str, Any]] = {}
        age_group = self._resolve_age_group()

        for indicator, raw_value in (lab_results or {}).items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue

            low, high = self._reference_bounds_by_age_group(indicator, age_group)

            severity = 0
            direction = "normal"
            if low is not None and value < low:
                direction = "low"
                if low <= 0:
                    severity = 1
                else:
                    ratio = (low - value) / low
                    if ratio <= 0.15:
                        severity = 1
                    elif ratio <= 0.35:
                        severity = 2
                    else:
                        severity = 3
            elif high is not None and value > high:
                direction = "high"
                if high <= 0:
                    severity = 1
                else:
                    ratio = (value - high) / high
                    if ratio <= 0.15:
                        severity = 1
                    elif ratio <= 0.35:
                        severity = 2
                    else:
                        severity = 3

            abnormal_bundle[indicator] = {
                "value": value,
                "low": low,
                "high": high,
                "direction": direction,
                "severity": severity,
                "is_abnormal": severity > 0,
            }

        return abnormal_bundle
    
    def _compute_gat_confidence(
        self,
        lab_results: Dict[str, float],
        abnormal_bundle: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, float]:
        """
        使用 GAT 计算各科室的置信度
        
        这里使用简化的启发式规则。在实际应用中，应该使用完整的 GAT 模型。
        
        Returns:
            {"肾内科": 0.7, "血液科": 0.6, ...}
        """
        # 初始化所有科室的置信度：只看指标名称是否在 lab_results 中出现
        current_weights = self.weight_updater.get_weights()
        confidence_scores = {}
        # GAT 仅基于指标名称存在性（不使用异常包或数值）
        
        # 简单规则：基于指标计算初始置信度
        # 这里的指标-科室映射和相关度分数是示例，实际应从数据库或配置加载
        indicator_deps = {
            # 肾内科
            "Cr": ("肾内科", 0.9),
            "BUN": ("肾内科", 0.85),
            "UREA": ("肾内科", 0.82),
            "UA": ("肾内科", 0.75),
            "CysC": ("肾内科", 0.88),
            "eGFR": ("肾内科", 0.9),
            "K": ("肾内科", 0.8),
            "Na": ("肾内科", 0.72),
            "Cl": ("肾内科", 0.68),
            "Ca": ("肾内科", 0.66),
            "Mg": ("肾内科", 0.64),
            "P": ("肾内科", 0.7),
            "PO4": ("肾内科", 0.7),

            # 血液科
            "WBC": ("血液科", 0.9),
            "RBC": ("血液科", 0.85),
            "Hb": ("血液科", 0.9),
            "PLT": ("血液科", 0.9),
            "HCT": ("血液科", 0.78),
            "MCV": ("血液科", 0.76),
            "MCH": ("血液科", 0.72),
            "MCHC": ("血液科", 0.72),
            "RDW": ("血液科", 0.7),
            "NRBC": ("血液科", 0.72),

            # 内分泌科
            "GLU": ("内分泌科", 0.9),
            "HbA1c": ("内分泌科", 0.85),
            "CHO": ("内分泌科", 0.72),
            "TG": ("内分泌科", 0.72),
            "TSH": ("内分泌科", 0.7),
            "T3": ("内分泌科", 0.66),
            "T4": ("内分泌科", 0.66),

            # 感染科
            "CRP": ("感染科", 0.9),
            "PCT": ("感染科", 0.92),
            "NEUT%": ("感染科", 0.82),
            "LYMPH%": ("感染科", 0.74),
            "NE": ("感染科", 0.8),
            "LY": ("感染科", 0.72),
            "MO": ("感染科", 0.68),
            "EO": ("感染科", 0.62),
            "BA": ("感染科", 0.6),
            "ALT": ("感染科", 0.65),
            "AST": ("感染科", 0.65),
            "GGT": ("感染科", 0.62),
            "ALP": ("感染科", 0.6),
            "TBIL": ("感染科", 0.7),
            "DBIL": ("感染科", 0.68),
            "TBA": ("感染科", 0.64),
            "CHE": ("感染科", 0.6),
            "TP": ("感染科", 0.58),
            "ALB": ("感染科", 0.62),
            "GLO": ("感染科", 0.58),
            "A/G": ("感染科", 0.58),
            "CK": ("感染科", 0.58),
            "LDH": ("感染科", 0.62),
            "α-HBD": ("感染科", 0.58),

            # 呼吸科
            "pH": ("呼吸科", 0.86),
            "pCO2": ("呼吸科", 0.86),
            "pO2": ("呼吸科", 0.9),
            "HCO3": ("呼吸科", 0.82),
            "O2Sat": ("呼吸科", 0.88),
            "CO2": ("呼吸科", 0.7),
        }
        
        # 计算各科室的置信度
        for dept in self.dept_agents.keys():
            dept_confidence = 0.0
            dept_indicator_count = 0
            
            for indicator, (dep, rel) in indicator_deps.items():
                # 仅基于指标名称存在性计算初始置信度，避免使用数值/严重度影响选科
                if dep == dept and indicator in lab_results:
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
        abnormal_bundle: Optional[Dict[str, Dict[str, Any]]] = None,
        user_history_text: str = "",
    ) -> Dict[str, Dict]:
        """构建主Agent下发给各科室的任务分配字段。"""
        abnormal_bundle = abnormal_bundle or self._compute_abnormal_bundle(lab_results)
        assignments: Dict[str, Dict] = {}
        for dept, agent in self.dept_agents.items():

            focus_indicators = [
                ind
                for ind in getattr(agent, "key_indicators", [])
                if ind in lab_results and bool((abnormal_bundle.get(ind) or {}).get("is_abnormal"))
            ]
            # 作用是让科室Agent即使在低置信度时也能看到相关异常指标，避免完全被过滤掉导致诊断无据可依的情况
            assignments[dept] = {
                "round": round_no,
                "task_goal": "围绕该患者最可能患什么病进行专科判断，先分析化验单指标和正常指标的偏差，查询专业知识库，给出诊断结论和分析依据，分析可能关联的科室指标和推荐检查。",
                "department": dept,
                "focus_indicators": focus_indicators,
                "abnormal_bundle": abnormal_bundle,
                "gate_confidence": round(gat_confidence.get(dept, 0.5), 4),
                "need_user_history": True,
                "user_history_text": user_history_text,
                "patient_profile": self.patient_profile,
                "clinical_prior": self.clinical_prior,
                "required_output": [
                    # 诊断结论：primary_diagnosis（必填，明确诊断或症候群，不能只描述症状），confidence（必填，0-1之间），clinical_interpretation（选填，诊断分析和依据），differential_diagnoses（选填，鉴别诊断列表），recommended_tests（选填，推荐检查列表）
                    "primary_diagnosis",
                    "confidence",
                    "clinical_interpretation",
                    "differential_diagnoses",
                    "recommended_tests",
                    "recommended_departments",
                    "history_relevance",  # 是否与病史有关，什么关系
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

# 主Agent核心方法：计算注意力权重、识别关键指标簇、执行主循环、更新权重、生成最终诊断、处理用户反馈等
    def _weighted_consensus(
        self,
        responses: Dict[str, Any],
        conflict_level,
    ) -> ConsensusResult:
        """临床先验 + 指标命中 + 科室权重 的加权共识。"""

        current_weights = self.weight_updater.get_weights()
        diagnosis_scores = defaultdict(float)
        diagnosis_supporters = defaultdict(list)

        def _diag_matches_prior(diag: str, prior: str) -> bool:
            d = (diag or "").lower()
            p = (prior or "").lower()
            if not d or not p:
                return False

            # 先尝试直接子串命中，避免明显同义文本被漏判。
            if d in p or p in d:
                return True

            def _extract_terms(text: str) -> Set[str]:
                terms: Set[str] = set()
                # 英文词：长度>=4，减少噪声。
                terms.update(re.findall(r"[a-z]{4,}", text))
                # 中文双字词片段：兼容无空格中文文本。
                for i in range(len(text) - 1):
                    seg = text[i:i + 2]
                    if all("\u4e00" <= ch <= "\u9fff" for ch in seg):
                        terms.add(seg)
                return terms

            diag_terms = _extract_terms(d)
            if not diag_terms:
                return False

            hit_count = sum(1 for term in diag_terms if term in p)
            return hit_count >= 1 and (hit_count / max(len(diag_terms), 1)) >= 0.2

        def _prior_match_bonus(diag: str, prior: str) -> float:
            return 0.12 if _diag_matches_prior(diag, prior) else 0.0

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
            prior_bonus = _prior_match_bonus(diag, self.clinical_prior)
            hit_bonus = min(hit_count * 0.02, 0.2)
            dept_weight = float(current_weights.get(dept, 0.5))

            weighted_score = (base_conf + prior_bonus + hit_bonus) * max(dept_weight, 0.1)
            if prior_virtual_diag and prior_virtual_score > 0:
                weighted_score *= 0.5

            diagnosis_scores[diag] += weighted_score
            diagnosis_supporters[diag].append(dept)

            self.logger.info(
                "[REASONING][主Agent] 共识打分 | 科室=%s 诊断=%s base=%.2f hit=%d bonus(prior=%.2f,hit=%.2f) weight=%.3f score=%.3f",
                dept,
                diag,
                base_conf,
                hit_count,
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
        if cr is not None and (not is_pediatric) and float(cr) < 40:
            issues.append(f"成人 Cr={cr} 显著偏低，需优先排查 OCR/单位/样本问题，暂不作为肾损伤阳性证据")

        return issues

    def _sanitize_lab_results_for_reasoning(
        self,
        lab_results: Dict[str, float],
        data_quality_issues: List[str],
    ) -> Tuple[Dict[str, float], List[str]]:
        """对高风险异常值做隔离，避免错误数据进入后续共识与选科。"""
        # 改为不再从推理数据中剔除任何指标，仅保留原始检验结果并返回空的 quarantined 列表。
        # 数据质量告警仍会在上层被记录，但不会影响后续共识/选科流程。
        sanitized = dict(lab_results or {})
        quarantined: List[str] = []
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
            abnormal_bundle = self._compute_abnormal_bundle(graph_labs)

            if not key_indicators:
                key_indicators = [
                    k
                    for k in graph_labs.keys()
                    if bool((abnormal_bundle.get(k) or {}).get("is_abnormal"))
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
            abnormal_bundle = self._compute_abnormal_bundle(lab_results or {})
            fallback_keys = [
                k
                for k in (lab_results or {}).keys()
                if bool((abnormal_bundle.get(k) or {}).get("is_abnormal"))
            ][:5]
            guidance["key_indicators"] = fallback_keys
            guidance["indicator_weights"] = {k: 0.5 for k in fallback_keys}
        return guidance

    def _derive_missing_tests(
        self,
        lab_results: Dict[str, float],
        responses: Dict[str, Any],
    ) -> List[str]:
        """基于多科室证据的动态补检推荐（打分排序），避免硬编码疾病清单。"""
        abnormal_bundle = self._compute_abnormal_bundle(lab_results or {})
        current_labs = set((lab_results or {}).keys())
        current_weights = self.weight_updater.get_weights()
        candidate_scores: Dict[str, float] = defaultdict(float)
        candidate_reasons: Dict[str, List[str]] = defaultdict(list)

        def _add_candidate(test_name: str, score: float, reason: str) -> None:
            t = str(test_name or "").strip()
            if not t:
                return
            if t in current_labs:
                return
            candidate_scores[t] += max(float(score), 0.0)
            candidate_reasons[t].append(reason)

        def _is_abn(indicator: str) -> bool:
            return bool((abnormal_bundle.get(indicator) or {}).get("is_abnormal"))

        # 1) 异常严重度驱动：优先建议复查高严重度异常指标，减少漏证据。
        for indicator, info in abnormal_bundle.items():
            severity = int((info or {}).get("severity", 0) or 0)
            if severity <= 0:
                continue
            _add_candidate(
                f"复查{indicator}",
                0.5 + min(severity * 0.2, 0.6),
                f"{indicator}异常严重度={severity}",
            )

        # 2) 科室回传驱动：融合各科 recommended_tests，按科室权重和置信度加权。
        for dept, resp in (responses or {}).items():
            dept_weight = float(current_weights.get(dept, 0.5))
            resp_conf = float(getattr(getattr(resp, "primary_diagnosis", None), "confidence", 0.5) or 0.5)
            base_score = max(dept_weight, 0.1) * max(resp_conf, 0.1)

            for t in getattr(resp, "recommended_tests", []) or []:
                _add_candidate(t, 0.7 * base_score, f"{dept}建议检查")

            handoff = getattr(resp, "handoff_to_main", {}) or {}
            for t in handoff.get("recommended_tests", []) or []:
                _add_candidate(t, 0.6 * base_score, f"{dept}回传建议")

            # 回传中若包含缺失关键指标，直接作为下一步补检项。
            for ind in handoff.get("missing_indicators", []) or []:
                _add_candidate(ind, 0.55 * base_score, f"{dept}关键指标缺失")

            # 由命中指标反推同科室关键指标缺口。
            hit_indicators = set(handoff.get("hit_indicators", []) or [])
            focus_indicators = set(
                ((getattr(resp, "task_assignment", {}) or {}).get("focus_indicators", []) or [])
            )
            for ind in (focus_indicators - hit_indicators):
                _add_candidate(ind, 0.35 * base_score, f"{dept}未命中关键指标")

        # 3) 临床先验作为轻量偏置（非固定疾病清单）。
        if self.clinical_prior:
            prior_tokens = re.findall(r"[a-z]{4,}|[\u4e00-\u9fff]{2,}", (self.clinical_prior or "").lower())
            for token in prior_tokens[:3]:
                _add_candidate(f"与“{token}”相关检查", 0.15, "临床先验补证")

        # 4) 如果候选太少，兜底给通用复核项，避免空结果。
        if len(candidate_scores) < 3:
            for t in ["CRP", "PCT", "尿常规", "胸部X线", "网织红细胞计数"]:
                _add_candidate(t, 0.1, "通用证据补全")

        # 5) 按综合得分排序，返回前8项。
        ranked = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
        top_tests = [t for t, _ in ranked[:8]]
        if top_tests:
            self.logger.info(
                "[REASONING][主Agent] 动态补检推荐: %s",
                [
                    {
                        "test": t,
                        "score": round(candidate_scores.get(t, 0.0), 3),
                        "reason": "|".join(candidate_reasons.get(t, [])[:2]),
                    }
                    for t in top_tests
                ],
            )
        return top_tests

    def _build_followup_questions(
        self,
        lab_results: Dict[str, float],
        consensus: Optional[ConsensusResult],
    ) -> List[str]:
        """生成下一轮要向用户追问的问题（工具动作）。"""
        qs: List[str] = []
        abnormal_bundle = self._compute_abnormal_bundle(lab_results or {})

        def _is_abn(indicator: str) -> bool:
            return bool((abnormal_bundle.get(indicator) or {}).get("is_abnormal"))

        if "WBC" in lab_results and _is_abn("WBC"):
            qs.append("近期是否有发热、咳嗽、咽痛或尿频尿痛等感染症状？")

        if "Hb" in lab_results and _is_abn("Hb"):
            qs.append("是否存在乏力、头晕、黑便或月经过多等失血相关症状？")

        if "Cr" in lab_results and _is_abn("Cr"):
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
                        snippet = query_medical_knowledge(keyword, scope="main")
                        observation["knowledge"].append({
                            "keyword": keyword,
                            "summary": (snippet or "")[:300],
                        })
                        self.logger.info(
                            "[ACTION][主Agent] 主动检索知识库关键词: %s | summary_chars=%d",
                            keyword,
                            len(snippet or ""),
                        )
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
        max_rounds: int = 5,
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

        user_history_text = ""
        try:
            user_history_text = query_user_medical_history(self.user_id) or ""
            if user_history_text:
                self.logger.info("[THOUGHT][主Agent] 已预取病史摘要(前120字): %s", user_history_text[:120])
        except Exception as exc:
            self.logger.warning("病史查询失败（任务分配与共识降级）: %s", exc)

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

            abnormal_bundle = self._compute_abnormal_bundle(reasoning_labs)
            gat_confidence = self._compute_gat_confidence(reasoning_labs, abnormal_bundle)
            task_assignments = self._build_task_assignments(
                reasoning_labs,
                gat_confidence,
                round_no,
                abnormal_bundle,
                user_history_text,
            )

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
        analysis_summary["recommended_departments"] = (
            (graph_guidance or {}).get("recommended_agents")
            or analysis_summary.get("supporting_departments", [])
        )

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
