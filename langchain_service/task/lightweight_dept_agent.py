"""
轻量级部门Agent基类 - 支持LLM调用版本

每个科室（如肾内科、血液科等）都继承此基类，
实现 analyze() 方法来分析指标并返回诊断。

特点：
- 接收指标 + GAT置信度
- 调用LLM进行智能诊断分析（Qwen）
- 查询医学知识库
- 返回标准化的 DepartmentAgentResponse
- 提供权重反馈给主Agent
"""

import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


import logging
import time
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
import re
from datetime import datetime

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from .dept_agent_response import DepartmentAgentResponse, DiagnosisEntry, WeightFeedback
from knowledge.reference_ranges import get_reference_range
from knowledge.tools import query_medical_knowledge, query_user_medical_history, set_current_user_id

logger = logging.getLogger(__name__)

_LAB_KEY_ALIAS = {
    "cr": "Cr",
    "creatinine": "Cr",
    "bun": "BUN",
    "urea": "UREA",
    "uric_acid": "UA",
    "ua": "UA",
    "cystatin_c": "CysC",
    "egfr": "eGFR",
    "k": "K",
    "potassium": "K",
    "sodium": "Na",
    "na": "Na",
    "chloride": "Cl",
    "cl": "Cl",
    "calcium": "Ca",
    "ca": "Ca",
    "magnesium": "Mg",
    "mg": "Mg",
    "po4": "PO4",
    "phosphorus": "PO4",
    "p": "PO4",
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
    "cholesterol": "CHO",
    "triglyceride": "TG",
    "total_protein": "TP",
    "albumin": "ALB",
    "globulin": "GLO",
    "a_g_ratio": "A/G",
    "total_bile_acid": "TBA",
    "cholinesterase": "CHE",
    "alp": "ALP",
    "ggt": "GGT",
    "total_bilirubin": "TBIL",
    "direct_bilirubin": "DBIL",
    "co2": "CO2",
    "ldh": "LDH",
    "creatine_kinase": "CK",
    "ck": "CK",
    "a_hbd": "α-HBD",
    "tsh": "TSH",
    "t3": "T3",
    "t4": "T4",
    "ph": "pH",
    "pco2": "pCO2",
    "po2": "pO2",
    "hco3": "HCO3",
    "o2sat": "O2Sat",
    "crp": "CRP",
    "pct": "PCT",
    "ne": "NE",
    "ly": "LY",
    "mo": "MO",
    "eo": "EO",
    "ba": "BA",
    "neut%": "NEUT%",
    "lymph%": "LYMPH%",
    "neut": "NEUT%",
    "lymph": "LYMPH%",
    "alt": "ALT",
    "ast": "AST",
    "ld": "LD",
}

_REF_CODE_ALIAS = {
    "Hb": "HB",
    "PO4": "P",
}


class LightweightDepartmentAgent(ABC):
    """
    要求：
    1) 必须逐项依据“值 vs 参考范围”判断方向：高于上限/低于下限/正常。
    2) 临床解释必须以具体**原始数值**为依据，例如示例格式："ALT 48.2 U/L (高于上限)"，若未引用原始数值，系统将自动降低该诊断置信度。
    3) 临床解释必须与方向一致：
        - 例如 Cr/CysC 在多数场景下“升高”才支持肾清除功能下降；若为“低于下限”，不得直接作为肾功能不全正证据。
        - K 仅在超出范围时才可讨论高钾或低钾风险；范围内不得渲染急性风险。
    4) 任何诊断若与核心指标方向矛盾，必须降置信度并在解释中明确写出“证据矛盾”。
    5) 缺失检测项目只能作为“证据不足”，不能当作阳性证据。
    6) 综合病史、临床先验、同侪意见与知识库信息。
    7) 证据不足时明确指出缺口并给出补检项，不要跨科下确定性结论。
    8) 仅输出JSON，不要输出额外说明文本。
    """

    def __init__(self, department_name: str, use_llm: bool = True):
        self.department_name = department_name
        self.key_indicators = []  # 本科室关键指标，子类应设置
        self.logger = logger
        self.use_llm = use_llm
        
        # 初始化LLM（如果启用）
        if self.use_llm:
            self.llm = ChatOpenAI(
                model=settings.DASHSCOPE_MODEL,
                openai_api_key=settings.DASHSCOPE_API_KEY,
                openai_api_base=settings.DASHSCOPE_BASE_URL,
                temperature=0.3,
                max_tokens=1200,
            )
        else:
            self.llm = None
        
        # 权重历史（用于反馈决策）
        self.call_count = 0
        self.success_count = 0
        self.avg_confidence = 0.5
    
    @abstractmethod
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """
        子类必须实现的核心分析逻辑
        
        Returns:
            (primary_diagnosis_name, primary_confidence, differential_diagnoses, clinical_interpretation)
        """
        pass
    
    def _retrieve_medical_knowledge(self, query: str = "", top_k: int = 3, indicator: Optional[str] = None, direction: Optional[str] = None) -> tuple[str, List[str]]:
        """检索医学知识库：仅走 tools 接口（单一路径，不降级）。

        支持按指标和方向（升高/降低/正常）增强查询以提升检索相关性。
        """
        _ = top_k  # 保留参数仅用于兼容历史调用
        try:
            # 若提供 indicator/direction，则优先按 indicator 组合查询
            if indicator:
                tool_query = f"{self.department_name} {indicator}".strip()
            else:
                tool_query = f"{self.department_name} {query}".strip()

            self.logger.info(
                "[%s] [ACTION] 知识检索开始 | query=%s direction=%s",
                self.department_name,
                tool_query[:160],
                direction,
            )
            summary = query_medical_knowledge(
                tool_query,
                scope="department",
                department=self.department_name,
                indicator=indicator,
                direction=direction,
            )
            if isinstance(summary, str) and summary.strip():
                self.logger.info(
                    "[%s] [OBSERVATION] 知识检索完成 | chars=%d",
                    self.department_name,
                    len(summary),
                )
                # 打印检索到的知识片段便于调试（最多1000字符）
                try:
                    self.logger.info("[%s] 知识摘要片段: %s", self.department_name, summary.strip()[:1000])
                except Exception:
                    pass
                return summary.strip(), ["Tool:QueryMedicalKnowledge"]
            self.logger.info("[%s] [OBSERVATION] 知识检索为空", self.department_name)
            return "", []
        except Exception as e:
            self.logger.warning(f"[{self.department_name}] tools知识检索失败: {e}")
            return "", []

    @staticmethod
    def _to_string_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _build_severity_map(
        self,
        lab_results: Dict[str, float],
        patient_profile: Optional[Dict[str, Any]],
        abnormal_bundle: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """构建指标严重度映射，优先复用主Agent异常包。"""
        severity_map: Dict[str, int] = {}
        if isinstance(abnormal_bundle, dict) and abnormal_bundle:
            for ind in self.key_indicators:
                if ind in lab_results:
                    severity_map[ind] = int((abnormal_bundle.get(ind) or {}).get("severity", 0) or 0)
            return severity_map

        for ind in self.key_indicators:
            if ind not in lab_results:
                continue
            try:
                val = float(lab_results[ind])
            except (TypeError, ValueError):
                continue
            severity_map[ind] = self._abnormality_severity(ind, val, patient_profile)
        return severity_map
    
    def _analyze_with_llm(
        self,
        lab_results: Dict[str, float],
        focused_lab_results: Dict[str, float],
        gat_confidence: float,
        knowledge_summary: str,
        user_history: str,
        task_assignment: Dict[str, Any],
        peer_observations: List[Dict[str, Any]],
        patient_profile: Dict[str, Any],
        clinical_prior: str,
        severity_map: Dict[str, int],
    ) -> Tuple[str, float, List[DiagnosisEntry], str, List[str], List[str], List[str]]:
        """
        使用LLM进行增强型自主推理。

        Returns:
            (主诊断, 置信度, 鉴别诊断, 临床解读, 推荐检查, 推荐科室, 缺失指标)
        """
        try:
            self.logger.info(
                "[%s] [THOUGHT] LLM推理准备 | focus=%d peer=%d history_len=%d prior=%s",
                self.department_name,
                len(focused_lab_results or {}),
                len(peer_observations or []),
                len(user_history or ""),
                bool(clinical_prior),
            )
            indicator_details: List[str] = []
            for ind in self.key_indicators:
                if ind in lab_results:
                    try:
                        val = float(lab_results[ind])
                    except (TypeError, ValueError):
                        val = lab_results[ind]
                    low, high = self._get_reference_bounds(ind, patient_profile)
                    sev = int(severity_map.get(ind, 0) or 0)
                    sev_text = ["正常", "轻度异常", "中度异常", "重度异常"][max(0, min(3, sev))]
                    direction = "正常"
                    if isinstance(val, (int, float, float)):
                        if low is not None and val < low:
                            direction = "低于下限"
                        elif high is not None and val > high:
                            direction = "高于上限"
                    indicator_details.append(
                        f"- {ind}: 值={lab_results[ind]}, 参考范围=[{low}, {high}], 方向={direction}, 程度={sev_text}"
                    )
                else:
                    indicator_details.append(f"- {ind}: 未检测")

            age = patient_profile.get("age_years", "未知")
            gender = patient_profile.get("gender", "未知")
            is_pediatric = self._is_pediatric_profile(patient_profile)

            peer_lines: List[str] = []
            for p in (peer_observations or [])[:5]:
                peer_lines.append(
                    f"- {p.get('department', '未知科室')}: 诊断={p.get('primary_diagnosis', '未知')} "
                    f"置信度={float(p.get('confidence', 0.0) or 0.0):.2f}, 命中指标={p.get('hit_indicators', [])}"
                )

            system_prompt = f"""你是{self.department_name}的资深专科医生，请进行自主推理并给出结构化结论。

要求：
1) 必须逐项依据“值 vs 参考范围”判断方向：高于上限/低于下限/正常。
2) 临床解释必须与方向一致：
    - 例如 Cr/CysC 在多数场景下“升高”才支持肾清除功能下降；若为“低于下限”，不得直接作为肾功能不全正证据。
    - K 仅在超出范围时才可讨论高钾或低钾风险；范围内不得渲染急性风险。
3) 任何诊断若与核心指标方向矛盾，必须降置信度并在解释中明确写出“证据矛盾”。
4) 缺失检测项目只能作为“证据不足”，不能当作阳性证据。
2) 综合病史、临床先验、同侪意见与知识库信息。
3) 证据不足时明确指出缺口并给出补检项，不要跨科下确定性结论。
4) 仅输出JSON，不要输出额外说明文本。

JSON结构：
{{
  "primary_diagnosis": "主诊断名称",
  "confidence": 0.0,
  "differential_diagnoses": [{{"diagnosis": "...", "confidence": 0.0}}],
  "clinical_interpretation": "详细推理过程",
  "recommended_tests": ["检查1", "检查2"],
  "recommended_departments": ["科室1"],
  "missing_indicators": ["指标1", "指标2"]
}}"""

            user_prompt = f"""请分析以下信息并输出JSON：

【本科室关键指标及异常程度】
{chr(10).join(indicator_details)}

【患者画像】
- 年龄: {age}
- 性别: {gender}
- 儿科患者: {is_pediatric}

【临床先验】
{clinical_prior or '无'}

【主Agent任务目标】
{task_assignment.get('task_goal', '围绕该患者最可能患什么病进行专科判断')}

【病史摘要】
{user_history or '无'}

【同侪观察】
{chr(10).join(peer_lines) if peer_lines else '无'}

【相关医学文献】
{knowledge_summary or '无'}

【GAT置信度】
{gat_confidence:.2f}
"""
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # 使用带重试的 LLM 调用以提高健壮性（处理短暂网络/限流）
            def _invoke_llm_with_retries(messages, attempts=3, backoff=1.0):
                last_err = None
                for i in range(1, attempts + 1):
                    try:
                        resp = self.llm.invoke(messages)
                        return resp
                    except Exception as exc:
                        last_err = exc
                        self.logger.warning(
                            "[%s] LLM 调用失败第%d次: %s",
                            self.department_name,
                            i,
                            str(exc),
                        )
                        if i < attempts:
                            time.sleep(backoff * (2 ** (i - 1)))
                # 最后仍然失败，抛出异常交由外层处理
                raise last_err

            response = _invoke_llm_with_retries(messages)
            content = str(getattr(response, 'content', response) or "")
            self.logger.info("[%s] [OBSERVATION] LLM返回长度=%d", self.department_name, len(content))
            # 记录原始返回以便排查（不打印过长内容）
            self.logger.debug("[%s] LLM原始返回（前1000字符）: %s", self.department_name, content[:1000])
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start < 0 or json_end <= json_start:
                raise ValueError("未找到有效JSON")

            result = json.loads(content[json_start:json_end])

            primary = str(result.get("primary_diagnosis", "诊断未确定") or "诊断未确定")
            confidence = float(result.get("confidence", 0.5) or 0.5)
            confidence = max(0.1, min(0.99, confidence))

            differential: List[DiagnosisEntry] = []
            for item in (result.get("differential_diagnoses", []) or []):
                if not isinstance(item, dict):
                    continue
                differential.append(DiagnosisEntry(
                    diagnosis=str(item.get("diagnosis", "") or ""),
                    confidence=float(item.get("confidence", 0.3) or 0.3),
                    clinical_evidence="LLM推理",
                ))

            clinical = str(result.get("clinical_interpretation", "") or "")
            # 强制检查：LLM 输出中必须包含相关指标的原始数值，否则衰减置信度
            try:
                vals_present = False
                for ind in self.key_indicators:
                    if ind in lab_results:
                        raw_val = lab_results[ind]
                        # 检查 clinical 文本是否包含该数值（简单文本匹配或格式化匹配）
                        if str(raw_val) in clinical:
                            vals_present = True
                            break
                        # 检查常见的格式化小数匹配
                        try:
                            if re.search(rf"\b{float(raw_val):.2f}\b", clinical):
                                vals_present = True
                                break
                        except Exception:
                            pass
                if not vals_present:
                    self.logger.info("[%s] LLM未引用原始数值，置信度衰减 0.7x", self.department_name)
                    confidence = max(0.1, round(confidence * 0.7, 2))
                    clinical = clinical + "\n（注意：输出未引用原始数值，已降低置信度）"
            except Exception:
                # 容错：不要因为校验逻辑导致失败
                pass
            recommended_tests = self._to_string_list(result.get("recommended_tests", []))
            recommended_departments = self._to_string_list(result.get("recommended_departments", []))
            missing_indicators = self._to_string_list(result.get("missing_indicators", []))

            self.logger.info(f"[{self.department_name}] LLM诊断: {primary} ({confidence:.2f})")
            self.logger.info(
                "[%s] [REASONING] LLM结构化输出 | differential=%d tests=%d depts=%d missing=%d",
                self.department_name,
                len(differential),
                len(recommended_tests),
                len(recommended_departments),
                len(missing_indicators),
            )
            return (
                primary,
                confidence,
                differential,
                clinical,
                recommended_tests,
                recommended_departments,
                missing_indicators,
            )
                
        except Exception as e:
            self.logger.warning(f"[{self.department_name}] LLM分析异常，返回失败态: {e}")
            return "智能推理失败", 0.0, [], "LLM调用失败，未执行启发式降级。", [], [], []

    def _filter_focus_lab_results(self, lab_results: Dict[str, float]) -> Dict[str, float]:
        """优先保留本科室关键指标，避免跨科指标干扰主判断。"""
        focused = {k: v for k, v in (lab_results or {}).items() if k in self.key_indicators}
        return focused

    def _normalize_lab_results(self, lab_results: Dict[str, float]) -> Dict[str, float]:
        """统一指标命名，确保科室关键指标命中。"""
        normalized: Dict[str, float] = {}
        for raw_key, raw_value in (lab_results or {}).items():
            key = str(raw_key).strip()
            mapped = _LAB_KEY_ALIAS.get(key.lower(), key)
            normalized[mapped] = raw_value
        return normalized

    def _is_pediatric_profile(self, patient_profile: Optional[Dict[str, Any]]) -> bool:
        age_years = float((patient_profile or {}).get("age_years", -1))
        return bool((patient_profile or {}).get("is_pediatric")) or (0 <= age_years < 14)

    def _get_reference_bounds(
        self,
        indicator: str,
        patient_profile: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[float], Optional[float]]:
        if self._is_pediatric_profile(patient_profile):
            pediatric_ranges = {
                "Cr": (15.0, 40.0),
                "BUN": (2.0, 7.0),
                "Hb": (95.0, 145.0),
                "HB": (95.0, 145.0),
                "PLT": (100.0, 350.0),
                "WBC": (5.0, 15.0),
                "TBIL": (0.0, 20.0),
                "DBIL": (0.0, 8.0),
            }
            p = pediatric_ranges.get(indicator)
            if p:
                return p

        code = _REF_CODE_ALIAS.get(indicator, indicator)
        ref = get_reference_range(code)
        if not ref:
            return None, None

        age_years = float((patient_profile or {}).get("age_years", -1) or -1)
        gender_raw = str((patient_profile or {}).get("gender", "") or "").strip().lower()
        if ("女" in gender_raw) or gender_raw.startswith("f"):
            gender_candidates = [ref.get("female"), ref.get("male")]
        elif ("男" in gender_raw) or gender_raw.startswith("m"):
            gender_candidates = [ref.get("male"), ref.get("female")]
        else:
            gender_candidates = [ref.get("male"), ref.get("female")]

        age_candidates: List[Optional[Dict[str, Any]]] = []
        if 15 <= age_years <= 18:
            age_candidates = [ref.get("adolescent"), ref.get("teen"), ref.get("pediatric")]
        elif age_years >= 65:
            age_candidates = [ref.get("elderly"), ref.get("geriatric"), ref.get("senior")]

        range_candidates = [
            *gender_candidates,
            *age_candidates,
            ref.get("fasting"),
            ref.get("optimal"),
            ref.get("postprandial"),
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

    def _abnormality_severity(
        self,
        indicator: str,
        value: float,
        patient_profile: Optional[Dict[str, Any]] = None,
    ) -> int:
        """0=正常,1=轻度,2=中度,3=重度。"""
        low, high = self._get_reference_bounds(indicator, patient_profile)
        if low is None and high is None:
            return 0

        if low is not None and value < low:
            if low <= 0:
                return 1
            ratio = (low - value) / low
            if ratio <= 0.15:
                return 1
            if ratio <= 0.35:
                return 2
            return 3

        if high is not None and value > high:
            if high <= 0:
                return 1
            ratio = (value - high) / high
            if ratio <= 0.15:
                return 1
            if ratio <= 0.35:
                return 2
            return 3

        return 0

    def _is_abnormal(
        self,
        indicator: str,
        value: float,
        patient_profile: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """仅将超出参考范围的指标视为命中，避免“有值即命中”的误导。"""
        return self._abnormality_severity(indicator, value, patient_profile) > 0

    def _apply_mild_abnormal_decay(
        self,
        confidence: float,
        essential_indicators: List[str],
        lab_results: Dict[str, float],
        patient_profile: Optional[Dict[str, Any]] = None,
        severity_map: Optional[Dict[str, int]] = None,
    ) -> float:
        """轻度异常时对过高置信度做衰减，降低单指标过拟合风险。"""
        if not essential_indicators:
            return confidence

        if severity_map:
            severities = [
                int(severity_map.get(ind, 0))
                for ind in essential_indicators
                if ind in severity_map
            ]
        else:
            severities = [
                self._abnormality_severity(ind, float(lab_results[ind]), patient_profile)
                for ind in essential_indicators
                if ind in lab_results
            ]
        if not severities:
            return confidence

        max_sev = max(severities)
        avg_sev = sum(severities) / len(severities)
        adjusted = confidence

        if max_sev <= 1:
            adjusted *= 0.72
            if len(essential_indicators) == 1:
                adjusted *= 0.85
        elif max_sev == 2 and avg_sev < 1.8:
            adjusted *= 0.9

        adjusted = max(0.35, min(0.98, adjusted))
        if adjusted != confidence:
            self.logger.info(
                "[%s] 轻度异常置信度衰减: %.3f -> %.3f | indicators=%s | severities=%s",
                self.department_name,
                confidence,
                adjusted,
                essential_indicators,
                severities,
            )
        return adjusted
    
    
    def _calculate_weight_feedback(
        self,
        primary_confidence: float,
        indicators_hit_rate: float,
        peer_observations: List[Dict[str, Any]],
        peer_agreement: bool = False,
    ) -> WeightFeedback:
        """增强权重反馈：置信度 + 命中率 + 同行一致性。"""
        self.call_count += 1
        self.success_count += 1

        conf_delta = (primary_confidence - 0.5) * 0.2
        hit_delta = (indicators_hit_rate - 0.5) * 0.1
        peer_delta = 0.0
        if peer_observations:
            if peer_agreement:
                peer_delta = 0.05
            elif primary_confidence < 0.6:
                peer_delta = -0.1

        my_weight_delta = max(-0.3, min(0.3, conf_delta + hit_delta + peer_delta))
        return WeightFeedback(
            my_weight_delta=my_weight_delta,
            adjustment_reason=(
                f"置信度={primary_confidence:.2f}, 命中率={indicators_hit_rate:.2f}, "
                f"同行一致={peer_agreement}, 调整={my_weight_delta:+.3f}"
            )
        )
    
    def analyze(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float = 0.5,
        context: Optional[Dict] = None,
        user_id: Optional[str] = None,
    ) -> DepartmentAgentResponse:
        """主分析入口（增强版）。"""
        start_time = time.time()
        lab_results = self._normalize_lab_results(lab_results)
        context = context or {}
        
        try:
            self.logger.info(
                f"[{self.department_name}] 分析开始 | "
                f"指标数: {len(lab_results)} | "
                f"GAT置信度: {gat_confidence:.2f}"
            )

            task_assignment = (context.get("task_assignments") or {}).get(self.department_name, {})
            patient_profile = (task_assignment or {}).get("patient_profile", {})
            clinical_prior = str((task_assignment or {}).get("clinical_prior", "") or "")
            peer_handoffs = context.get("peer_handoffs", {}) or {}
            peer_observations = []
            for dept, handoff in peer_handoffs.items():
                if isinstance(handoff, dict) and handoff:
                    peer_observations.append({
                        "department": dept,
                        "primary_diagnosis": handoff.get("primary_diagnosis", ""),
                        "confidence": handoff.get("confidence", 0.0),
                        "hit_indicators": handoff.get("hit_indicators", []),
                    })
            if task_assignment:
                self.logger.info(f"[{self.department_name}] [ACTION] 收到主Agent任务分配: {task_assignment}")
            if peer_observations:
                self.logger.info(f"[{self.department_name}] [OBSERVATION] 收到同侪摘要: {peer_observations}")
            self.logger.info(
                "[%s] [THOUGHT] 上下文摘要 | prior=%s peer_count=%d",
                self.department_name,
                bool(clinical_prior),
                len(peer_observations),
            )

            # 0. 需要时访问用户信息工具（主Agent与科室Agent共享）
            user_history = ""
            try:
                set_current_user_id(user_id)
                need_user_history = bool(context.get("need_user_history")) or gat_confidence >= 0.6
                if need_user_history:
                    user_history = query_user_medical_history(user_id) or ""
                    self.logger.info(f"[{self.department_name}] 已通过工具获取用户信息")
                    if user_history:
                        self.logger.info(
                            f"[{self.department_name}] [OBSERVATION] 病史摘要(前120字): {user_history[:120]}"
                        )
                    self.logger.info(
                        "[%s] [OBSERVATION] 病史查询完成 | need=%s len=%d",
                        self.department_name,
                        need_user_history,
                        len(user_history),
                    )
            except Exception as e:
                self.logger.warning(f"[{self.department_name}] 获取用户信息失败: {e}")
            
            # 1. 关键指标与异常严重度
            abnormal_bundle = (task_assignment or {}).get("abnormal_bundle")
            severity_map = self._build_severity_map(lab_results, patient_profile, abnormal_bundle)
            essential_indicators = [
                ind for ind in self.key_indicators
                if ind in lab_results and int(severity_map.get(ind, 0) or 0) > 0
            ]
            indicators_hit_rate = len(essential_indicators) / len(self.key_indicators) if self.key_indicators else 0.5
            focused_lab_results = self._filter_focus_lab_results(lab_results)
            self.logger.info(
                f"[{self.department_name}] [THOUGHT] 以本科关键指标推断主病种 | "
                f"关键命中={essential_indicators or []} | 聚焦指标数={len(focused_lab_results)}"
            )
            self.logger.info(
                "[%s] [OBSERVATION] 严重度映射=%s",
                self.department_name,
                severity_map,
            )
            
            # 2. 知识库检索（优先最异常指标），并带上方向信息以提高检索相关性
            sensitive_indicators = [ind for ind in essential_indicators if ind in lab_results]
            if sensitive_indicators:
                primary_ind = sensitive_indicators[0]
                # 尝试从 task_assignment 的 abnormal_bundle 中读取方向
                abn = (task_assignment or {}).get("abnormal_bundle") or {}
                direction = None
                if isinstance(abn, dict) and primary_ind in abn:
                    direction = (abn.get(primary_ind) or {}).get("direction")
                knowledge_summary, knowledge_sources = self._retrieve_medical_knowledge(
                    indicator=primary_ind,
                    direction=direction,
                )
            else:
                knowledge_summary, knowledge_sources = "", []
            self.logger.info(
                "[%s] [OBSERVATION] 知识检索摘要 | query_indicators=%s chars=%d sources=%s",
                self.department_name,
                sensitive_indicators,
                len(knowledge_summary or ""),
                knowledge_sources,
            )
            
            # 3. 核心推理：仅允许LLM智能路径，不做启发式降级
            if self.use_llm and self.llm:
                primary_diagnosis_name, primary_confidence, differential_diagnoses, clinical_interpretation, recommended_tests, recommended_departments, missing_indicators = \
                    self._analyze_with_llm(
                        lab_results,
                        focused_lab_results,
                        gat_confidence,
                        knowledge_summary,
                        user_history,
                        task_assignment,
                        peer_observations,
                        patient_profile,
                        clinical_prior,
                        severity_map,
                    )
            else:
                return self._create_fallback_response(
                    lab_results,
                    "LLM未启用或不可用，启发式已禁用",
                    time.time() - start_time,
                )

            if not missing_indicators:
                missing_indicators = [ind for ind in self.key_indicators if ind not in lab_results][:5]
            self.logger.info(
                "[%s] [REASONING] 推理输出摘要 | diag=%s conf=%.3f missing=%s",
                self.department_name,
                primary_diagnosis_name,
                primary_confidence,
                missing_indicators,
            )

            peer_agreement = False
            if peer_observations and primary_diagnosis_name:
                pdiag = str(primary_diagnosis_name)
                for p in peer_observations:
                    other = str(p.get("primary_diagnosis", "") or "")
                    if pdiag and other and (pdiag in other or other in pdiag):
                        peer_agreement = True
                        break
            
            # 4. 构建主诊断
            primary_diagnosis = DiagnosisEntry(
                diagnosis=primary_diagnosis_name,
                confidence=primary_confidence,
                clinical_evidence=f"基于 {', '.join(essential_indicators)} 分析"
            )
            
            # 5. 权重反馈
            weight_feedback = self._calculate_weight_feedback(
                primary_confidence,
                indicators_hit_rate,
                peer_observations,
                peer_agreement,
            )
            
            # 6. 构建响应
            handoff_to_main = {
                "department": self.department_name,
                "task_goal": task_assignment.get("task_goal", "围绕主病种做专科判断"),
                "focused_indicators": list(focused_lab_results.keys()),
                "hit_indicators": essential_indicators,
                "primary_diagnosis": primary_diagnosis_name,
                "confidence": round(primary_confidence, 4),
                "differential_count": len(differential_diagnoses),
                "clinical_interpretation": clinical_interpretation,
                "recommended_tests": recommended_tests,
                "recommended_departments": recommended_departments,
                "missing_indicators": missing_indicators,
                "history_used": bool(user_history),
                "history_excerpt": user_history[:120] if user_history else "",
                "peer_observation_used": bool(peer_observations),
                "peer_agreement": peer_agreement,
                "reasoning_trace": (clinical_interpretation or "")[:200],
            }
            response = DepartmentAgentResponse(
                department=self.department_name,
                analysis_time=time.time() - start_time,
                primary_diagnosis=primary_diagnosis,
                differential_diagnoses=differential_diagnoses,
                knowledge_summary=knowledge_summary,
                knowledge_sources=knowledge_sources,
                weight_feedback=weight_feedback,
                clinical_interpretation=clinical_interpretation,
                recommended_tests=recommended_tests,
                task_assignment=task_assignment,
                handoff_to_main=handoff_to_main,
            )
            self.logger.info(f"[{self.department_name}] [OBSERVATION] 回传主Agent内容: {handoff_to_main}")
            
            self.logger.info(
                f"[{self.department_name}] 分析完成 | "
                f"诊断: {primary_diagnosis_name} ({primary_confidence:.1%}) | "
                f"耗时: {response.analysis_time:.3f}s"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"[{self.department_name}] 分析异常: {e}", exc_info=True)
            # 返回降级响应
            return self._create_fallback_response(lab_results, str(e), time.time() - start_time)
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        """获取推荐检查项，子类可重写"""
        return []
    
    def _create_fallback_response(self, lab_results: Dict[str, float], error: str, elapsed: float) -> DepartmentAgentResponse:
        """创建降级响应（分析失败时）"""
        return DepartmentAgentResponse(
            department=self.department_name,
            analysis_time=elapsed,
            primary_diagnosis=DiagnosisEntry(
                diagnosis="分析异常",
                confidence=0.0,
                clinical_evidence=error
            ),
            weight_feedback=WeightFeedback(
                my_weight_delta=-0.2,  # 失败时权重下调
                adjustment_reason="分析异常，自动下调权重"
            ),
            warnings=[f"分析异常: {error}"]
        )


# 示例：肾内科 Agent
class NephrologyAgent(LightweightDepartmentAgent):
    """肾内科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("肾内科", use_llm=use_llm)
        self.key_indicators = ["Cr", "BUN", "UREA", "UA", "CysC", "eGFR", "K", "Na", "Cl", "Ca", "Mg", "PO4"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """启发式已禁用，仅保留接口兼容。"""
        return "启发式已禁用", 0.0, [], "已禁用规则诊断，仅允许LLM智能推理。"
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        return []


# 示例：血液科 Agent
class HematologyAgent(LightweightDepartmentAgent):
    """血液科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("血液科", use_llm=use_llm)
        self.key_indicators = ["WBC", "RBC", "Hb", "PLT", "HCT", "MCV", "MCH", "MCHC", "RDW", "NRBC"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """启发式已禁用，仅保留接口兼容。"""
        return "启发式已禁用", 0.0, [], "已禁用规则诊断，仅允许LLM智能推理。"
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        return []


# ============================================================================
# 新增科室Agent：内分泌科
# ============================================================================

class EndocrinologyAgent(LightweightDepartmentAgent):
    """内分泌科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("内分泌科", use_llm=use_llm)
        self.key_indicators = ["GLU", "HbA1c", "TSH", "T3", "T4", "CHO", "TG"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """启发式已禁用，仅保留接口兼容。"""
        return "启发式已禁用", 0.0, [], "已禁用规则诊断，仅允许LLM智能推理。"
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        return []


# ============================================================================
# 新增科室Agent：呼吸科
# ============================================================================

class PulmonaryAgent(LightweightDepartmentAgent):
    """呼吸科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("呼吸科", use_llm=use_llm)
        self.key_indicators = ["pH", "pCO2", "pO2", "HCO3", "O2Sat", "CO2"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """启发式已禁用，仅保留接口兼容。"""
        return "启发式已禁用", 0.0, [], "已禁用规则诊断，仅允许LLM智能推理。"
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        return []


# ============================================================================
# 新增科室Agent：感染科
# ============================================================================

class InfectiousAgent(LightweightDepartmentAgent):
    """感染科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("感染科", use_llm=use_llm)
        self.key_indicators = [
            "WBC", "CRP", "PCT", "NEUT%", "LYMPH%", "NE", "LY", "MO", "EO", "BA",
            "ALT", "AST", "GGT", "ALP", "TBIL", "DBIL", "TBA", "CHE", "TP", "ALB", "GLO", "A/G", "CK", "LDH", "α-HBD"
        ]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """启发式已禁用，仅保留接口兼容。"""
        return "启发式已禁用", 0.0, [], "已禁用规则诊断，仅允许LLM智能推理。"
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        return []

