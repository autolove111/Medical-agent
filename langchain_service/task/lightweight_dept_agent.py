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

import logging
import time
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from .dept_agent_response import DepartmentAgentResponse, DiagnosisEntry, WeightFeedback
from knowledge.reference_ranges import get_reference_range
from tools import query_user_medical_history, set_current_user_id

logger = logging.getLogger(__name__)

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
    "plt": "PLT",
    "mcv": "MCV",
    "glu": "GLU",
    "glucose": "GLU",
    "hba1c": "HbA1c",
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
    轻量级科室Agent基类 - 支持LLM
    
    设计原则：
    1. 职责单一：只负责分析化验指标 → 返回诊断
    2. LLM增强：调用Qwen进行智能诊断
    3. 知识库支持：融合医学知识库
    4. 权重反馈：提供对自身及同行权重的建议
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
                temperature=0.5,  # 降低随机性，保证医学准确性
                max_tokens=1000,
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
    
    def _retrieve_medical_knowledge(self, query: str, top_k: int = 3) -> tuple[str, List[str]]:
        """检索医学知识库（共享接口）"""
        try:
            from knowledge.shared_knowledge_retriever import retrieve_by_department
            docs = retrieve_by_department(self.department_name, query, top_k=top_k)
            sources = [f"Doc-{i}" for i in range(len(docs))]
            summary = "\n".join(docs[:2]) if docs else "无相关文献"
            return summary, sources
        except Exception as e:
            self.logger.warning(f"[{self.department_name}] 知识库检索失败: {e}")
            return "", []
    
    def _analyze_with_llm(
        self,
        lab_results: Dict[str, float],
        focused_lab_results: Dict[str, float],
        gat_confidence: float,
        knowledge_summary: str,
        user_history: str = "",
        task_assignment: Optional[Dict[str, Any]] = None,
        peer_observations: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """
        使用LLM进行智能诊断分析
        
        Returns:
            (primary_diagnosis, confidence, differential_diagnoses, clinical_interpretation)
        """
        try:
            task_assignment = task_assignment or {}
            # 构建LLM提示
            system_prompt = f"""你是{self.department_name}的专科医生。
你的唯一核心任务：围绕“该患者最可能患什么病”进行专科判断，并给出需要排除的鉴别诊断。
优先使用本科室关键指标，不要被非本科室指标主导结论。
如果本科室关键指标缺失，请明确说明“证据不足”，并给出本科室需要补充的检查项；不要跨科给出确定性诊断。

必须返回JSON格式的诊断结果：
{{
  "primary_diagnosis": "主诊断名称",
  "confidence": 0.8,
  "differential_diagnoses": [
    {{"diagnosis": "鉴别诊断1", "confidence": 0.6}},
    {{"diagnosis": "鉴别诊断2", "confidence": 0.4}}
  ],
  "clinical_interpretation": "临床解读"
}}"""
            
            # 准备化验数据文本
            focus_lab_text = "\n".join([f"• {k}: {v}" for k, v in sorted(focused_lab_results.items())])
            assignment_text = json.dumps(task_assignment, ensure_ascii=False)
            peer_lines = []
            for peer in (peer_observations or [])[:4]:
                peer_lines.append(
                    f"- {peer.get('department', '未知科室')}: 诊断={peer.get('primary_diagnosis', '未知')} "
                    f"置信度={peer.get('confidence', 0)} 关注指标={peer.get('hit_indicators', [])}"
                )
            peer_text = "\n".join(peer_lines) if peer_lines else "无"
            
            user_prompt = f"""请分析以下患者化验数据：

【主分析指标（本科室）】
{focus_lab_text or '无本科室关键指标，需谨慎低置信输出'}

相关医学文献：
{knowledge_summary}

用户既往史与过敏信息：
{user_history or '暂无可用用户病史'}

主Agent任务分配：
{assignment_text}

其他科室观察（用于多学科协作修正，不可盲从）：
{peer_text}

GAT置信度：{gat_confidence:.1%}

请提供诊断意见（返回JSON格式）。"""
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # 解析LLM返回的JSON
            content = response.content
            try:
                # 尝试提取JSON
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    result = json.loads(json_str)
                else:
                    raise ValueError("未找到JSON格式")
                
                primary = result.get("primary_diagnosis", "诊断未确定")
                confidence = float(result.get("confidence", 0.5))
                
                # 解析鉴别诊断
                differential = []
                for item in result.get("differential_diagnoses", []):
                    differential.append(DiagnosisEntry(
                        diagnosis=item.get("diagnosis", ""),
                        confidence=float(item.get("confidence", 0.3)),
                        clinical_evidence="LLM分析"
                    ))
                
                clinical = result.get("clinical_interpretation", "")
                
                self.logger.info(f"[{self.department_name}] LLM诊断: {primary} ({confidence:.1%})")
                
                return primary, confidence, differential, clinical
                
            except json.JSONDecodeError as e:
                self.logger.warning(f"[{self.department_name}] JSON解析失败: {e}")
                # 降级使用启发式规则
                return self._analyze_indicators(lab_results, gat_confidence)
                
        except Exception as e:
            self.logger.error(f"[{self.department_name}] LLM分析异常: {e}", exc_info=True)
            # 降级使用启发式规则
            return self._analyze_indicators(lab_results, gat_confidence)

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
    ) -> float:
        """轻度异常时对过高置信度做衰减，降低单指标过拟合风险。"""
        if not essential_indicators:
            return confidence

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
        indicators_hit_rate: float,  # 有多少比例的关键指标被激活
    ) -> WeightFeedback:
        """
        计算权重调整反馈
        
        规则：
        - 高置信度 + 高指标命中率 → 权重↑
        - 低置信度 或 指标缺失 → 权重↓
        """
        # 更新统计
        self.call_count += 1
        self.success_count += 1
        
        # 计算权重调整
        confidence_delta = (primary_confidence - 0.5) * 0.2  # 基于置信度
        indicator_delta = (indicators_hit_rate - 0.5) * 0.1   # 基于指标命中
        
        my_weight_delta = confidence_delta + indicator_delta
        
        # 限制范围
        my_weight_delta = max(-0.3, min(0.3, my_weight_delta))
        
        return WeightFeedback(
            my_weight_delta=my_weight_delta,
            adjustment_reason=(
                f"置信度 {primary_confidence:.1%}, "
                f"指标命中 {indicators_hit_rate:.1%}, "
                f"建议权重调整 {my_weight_delta:+.3f}"
            )
        )
    
    def analyze(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float = 0.5,
        context: Optional[Dict] = None,  # 其他科室的结果（可选）
        user_id: Optional[str] = None,
    ) -> DepartmentAgentResponse:
        """
        主分析入口
        
        Args:
            lab_results: 化验指标字典，如 {"Cr": 120, "BUN": 25, ...}
            gat_confidence: GAT对该科室的置信度（0-1）
            context: 其他科室的分析结果（用于参考）
        
        Returns:
            DepartmentAgentResponse
        """
        start_time = time.time()
        lab_results = self._normalize_lab_results(lab_results)
        
        try:
            self.logger.info(
                f"[{self.department_name}] 分析开始 | "
                f"指标数: {len(lab_results)} | "
                f"GAT置信度: {gat_confidence:.2f}"
            )

            task_assignment = ((context or {}).get("task_assignments") or {}).get(self.department_name, {})
            patient_profile = (task_assignment or {}).get("patient_profile", {})
            peer_handoffs = (context or {}).get("peer_handoffs", {}) or {}
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

            # 0. 需要时访问用户信息工具（主Agent与科室Agent共享）
            user_history = ""
            try:
                set_current_user_id(user_id)
                need_user_history = bool((context or {}).get("need_user_history")) or gat_confidence >= 0.6
                if need_user_history:
                    user_history = query_user_medical_history(user_id)
                    self.logger.info(f"[{self.department_name}] 已通过工具获取用户信息")
                    if user_history:
                        self.logger.info(
                            f"[{self.department_name}] [OBSERVATION] 病史摘要(前120字): {user_history[:120]}"
                        )
            except Exception as e:
                self.logger.warning(f"[{self.department_name}] 获取用户信息失败: {e}")
            
            # 1. 检查关键指标
            essential_indicators = [
                ind
                for ind in self.key_indicators
                if ind in lab_results and self._is_abnormal(ind, float(lab_results[ind]), patient_profile)
            ]
            indicators_hit_rate = len(essential_indicators) / len(self.key_indicators) if self.key_indicators else 0.5
            focused_lab_results = self._filter_focus_lab_results(lab_results)
            self.logger.info(
                f"[{self.department_name}] [THOUGHT] 以本科关键指标推断主病种 | "
                f"关键命中={essential_indicators or []} | 聚焦指标数={len(focused_lab_results)}"
            )
            
            # 2. 知识库检索（优先）
            # 如果有关键指标异常，就先检索相关文献
            sensitive_indicators = [ind for ind in essential_indicators if ind in lab_results]
            if sensitive_indicators:
                knowledge_query = f"{self.department_name} {sensitive_indicators[0]}"
                knowledge_summary, knowledge_sources = self._retrieve_medical_knowledge(knowledge_query)
            else:
                knowledge_summary, knowledge_sources = "", []
            
            # 3. 核心分析（根据是否启用LLM）
            if not essential_indicators:
                primary_diagnosis_name = f"{self.department_name}证据不足"
                primary_confidence = 0.35
                differential_diagnoses = []
                clinical_interpretation = "本科室关键指标未命中，当前证据不足，建议补充本科室关键检查后再评估。"
            elif self.use_llm and self.llm:
                # 使用LLM进行智能诊断
                primary_diagnosis_name, primary_confidence, differential_diagnoses, clinical_interpretation = \
                    self._analyze_with_llm(
                        lab_results,
                        focused_lab_results,
                        gat_confidence,
                        knowledge_summary,
                        user_history,
                        task_assignment,
                        peer_observations,
                    )
            else:
                # 使用启发式规则
                primary_diagnosis_name, primary_confidence, differential_diagnoses, clinical_interpretation = \
                    self._analyze_indicators(lab_results, gat_confidence)

            primary_confidence = self._apply_mild_abnormal_decay(
                primary_confidence,
                essential_indicators,
                lab_results,
                patient_profile,
            )
            
            # 4. 构建主诊断
            primary_diagnosis = DiagnosisEntry(
                diagnosis=primary_diagnosis_name,
                confidence=primary_confidence,
                clinical_evidence=f"基于 {', '.join(essential_indicators)} 分析"
            )
            
            # 5. 权重反馈
            weight_feedback = self._calculate_weight_feedback(
                primary_confidence,
                indicators_hit_rate
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
                "recommended_tests": self._get_recommended_tests(lab_results, primary_diagnosis_name),
                "history_used": bool(user_history),
                "history_excerpt": user_history[:120] if user_history else "",
                "peer_observation_used": bool(peer_observations),
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
                recommended_tests=handoff_to_main["recommended_tests"],
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
        self.key_indicators = ["Cr", "BUN", "eGFR", "K", "PO4"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """肾内科分析逻辑"""
        
        cr = lab_results.get("Cr", 80)
        bun = lab_results.get("BUN", 7)
        egfr = lab_results.get("eGFR", 60)
        k = lab_results.get("K", 4.0)
        
        # 简单的启发式规则
        if cr > 133 or egfr < 30:
            primary = "慢性肾脏病3-5期"
            confidence = min(0.95, 0.7 + (cr - 133) / 200)
        elif cr > 106 and bun > 20:
            primary = "肾功能不全"
            confidence = 0.75
        elif k > 5.5:
            primary = "高钾血症"
            confidence = 0.85
        else:
            primary = "肾功能基本正常"
            confidence = 0.6
        
        # 鉴别诊断
        differential = []
        if bun > 20:
            differential.append(DiagnosisEntry("急性肾损伤", 0.5, "BUN升高"))
        if k > 5.0:
            differential.append(DiagnosisEntry("继发性高钾血症", 0.4, "K升高"))
        
        clinical = f"患者 Cr={cr} (↑)，eGFR={egfr} (↓)，BUN={bun}，K={k}。"
        
        return primary, confidence, differential, clinical
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        """推荐检查"""
        if lab_results.get("Cr", 0) > 120:
            return ["肾脏超声", "肾功能分级", "尿蛋白定量", "24小时尿肌酐"]
        return ["尿常规", "肾脏彩超"]


# 示例：血液科 Agent
class HematologyAgent(LightweightDepartmentAgent):
    """血液科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("血液科", use_llm=use_llm)
        self.key_indicators = ["WBC", "RBC", "Hb", "PLT", "MCV"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """血液科分析逻辑"""
        
        wbc = lab_results.get("WBC", 7)
        rbc = lab_results.get("RBC", 4.5)
        hb = lab_results.get("Hb", 130)
        plt = lab_results.get("PLT", 200)
        
        # 启发式规则
        if hb < 100:
            primary = "贫血"
            confidence = 0.85 - (100 - hb) / 1000
        elif wbc > 11 or wbc < 3.5:
            primary = "白细胞异常"
            confidence = 0.8
        elif plt < 100:
            primary = "血小板减少症"
            confidence = 0.9
        else:
            primary = "血细胞计数正常"
            confidence = 0.7
        
        differential = []
        if hb < 90 and rbc < 3.5:
            differential.append(DiagnosisEntry("缺铁性贫血", 0.6, "RBC/Hb↓"))
        
        clinical = f"WBC={wbc}, Hb={hb}, PLT={plt}"
        
        return primary, confidence, differential, clinical
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        if lab_results.get("Hb", 0) < 100:
            return ["血清铁", "铁蛋白", "红细胞体积分布宽度"]
        return ["外周血涂片"]


# ============================================================================
# 新增科室Agent：内分泌科
# ============================================================================

class EndocrinologyAgent(LightweightDepartmentAgent):
    """内分泌科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("内分泌科", use_llm=use_llm)
        self.key_indicators = ["GLU", "HbA1c", "TSH", "T3", "T4"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """内分泌科分析逻辑（启发式规则，用于LLM失败时降级）"""
        
        glu = lab_results.get("GLU", 90)
        hba1c = lab_results.get("HbA1c", 5.5)
        tsh = lab_results.get("TSH", 2.5)
        
        if glu > 126 or hba1c > 6.5:
            primary = "糖尿病"
            confidence = 0.8
        elif tsh < 0.5 or tsh > 5.0:
            primary = "甲状腺功能异常"
            confidence = 0.75
        else:
            primary = "内分泌功能基本正常"
            confidence = 0.6
        
        differential = []
        if glu > 100 and hba1c < 6.5:
            differential.append(DiagnosisEntry("糖耐量异常", 0.5, "空腹血糖升高"))
        
        clinical = f"患者 GLU={glu}, HbA1c={hba1c}, TSH={tsh}"
        
        return primary, confidence, differential, clinical
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        if lab_results.get("GLU", 0) > 100:
            return ["口服葡萄糖耐量试验", "C肽", "胰岛素"]
        return ["甲功三项检查"]


# ============================================================================
# 新增科室Agent：呼吸科
# ============================================================================

class PulmonaryAgent(LightweightDepartmentAgent):
    """呼吸科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("呼吸科", use_llm=use_llm)
        self.key_indicators = ["pH", "pCO2", "pO2", "HCO3", "O2Sat"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """呼吸科分析逻辑（启发式规则，用于LLM失败时降级）"""
        
        po2 = lab_results.get("pO2", 95)
        pco2 = lab_results.get("pCO2", 35)
        ph = lab_results.get("pH", 7.35)
        
        if po2 < 60:
            primary = "严重低氧血症"
            confidence = 0.9
        elif pco2 > 50:
            primary = "呼吸型酸中毒"
            confidence = 0.85
        elif ph < 7.35:
            primary = "酸中毒"
            confidence = 0.8
        else:
            primary = "呼吸功能基本正常"
            confidence = 0.6
        
        differential = []
        if po2 < 80 and pco2 > 45:
            differential.append(DiagnosisEntry("肺部疾病综合症", 0.6, "低氧高碳酸"))
        
        clinical = f"患者 pO2={po2}, pCO2={pco2}, pH={ph}"
        
        return primary, confidence, differential, clinical
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        if lab_results.get("pO2", 0) < 60:
            return ["胸部X光", "CT肺部扫描", "肺功能检查"]
        return ["胸部检查", "血气分析"]


# ============================================================================
# 新增科室Agent：感染科
# ============================================================================

class InfectiousAgent(LightweightDepartmentAgent):
    """感染科智能体 - 使用LLM进行诊断"""
    
    def __init__(self, use_llm: bool = True):
        super().__init__("感染科", use_llm=use_llm)
        self.key_indicators = ["WBC", "CRP", "PCT", "NEUT%", "LYMPH%"]
    
    def _analyze_indicators(
        self,
        lab_results: Dict[str, float],
        gat_confidence: float
    ) -> tuple[str, float, List[DiagnosisEntry], str]:
        """感染科分析逻辑（启发式规则，用于LLM失败时降级）"""
        
        wbc = lab_results.get("WBC", 7)
        crp = lab_results.get("CRP", 5)
        pct = lab_results.get("PCT", 0.05)
        
        if wbc > 15 and crp > 100:
            primary = "细菌感染"
            confidence = 0.85
        elif wbc < 3 and crp > 50:
            primary = "病毒感染"
            confidence = 0.75
        elif pct > 0.5:
            primary = "脓毒血症风险"
            confidence = 0.8
        else:
            primary = "无明显感染迹象"
            confidence = 0.6
        
        differential = []
        if crp > 50 and wbc > 10:
            differential.append(DiagnosisEntry("全身炎症反应综合征", 0.6, "炎症指标升高"))
        
        clinical = f"患者 WBC={wbc}, CRP={crp}, PCT={pct}"
        
        return primary, confidence, differential, clinical
    
    def _get_recommended_tests(self, lab_results: Dict[str, float], diagnosis: str) -> List[str]:
        if lab_results.get("CRP", 0) > 100:
            return ["血培养", "尿培养", "各部位分泌物培养"]
        return ["常规血液检查", "感染标记物检查"]

