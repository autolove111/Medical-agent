from typing import Any, Dict


def parse_report(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    lab_results = agent._normalize_lab_results(state.get("lab_results", {}))
    patient_profile = state.get("patient_profile", {}) or {}
    clinical_prior = state.get("clinical_prior", "") or ""

    agent.patient_profile = patient_profile
    agent.clinical_prior = clinical_prior
    agent.logger.info("[THOUGHT][主Agent] 归一化后检验指标=%s", dict(sorted(lab_results.items())))
    if patient_profile:
        agent.logger.info("[THOUGHT][主Agent] 患者画像=%s", patient_profile)
    if clinical_prior:
        agent.logger.info("[THOUGHT][主Agent] 临床先验诊断=%s", clinical_prior)

    data_quality_issues = agent._detect_data_quality_issues(lab_results)
    if data_quality_issues:
        agent.logger.warning("[OBSERVATION][主Agent] 数据质量告警: %s", data_quality_issues)

    reasoning_labs, quarantined_indicators = agent._sanitize_lab_results_for_reasoning(
        lab_results,
        data_quality_issues,
    )

    return {
        "lab_results": lab_results,
        "user_history_text": agent._get_user_history_text(),
        "data_quality_issues": data_quality_issues,
        "quarantined_indicators": quarantined_indicators,
        "reasoning_labs": reasoning_labs,
        "all_responses": {},
        "used_departments": [],
        "react_rounds": [],
        "current_round": 1,
        "should_stop": False,
        "stop_reason": "",
        "round_responses": {},
        "weight_updates": {},
        "department_weight_history": agent.weight_updater.get_weights(),
    }
