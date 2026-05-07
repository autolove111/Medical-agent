from typing import Any, Dict


def write_conclusion(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    all_responses = state.get("all_responses", {}) or {}
    consensus = state.get("consensus")
    conflict_report = state.get("conflict_report")
    if not all_responses or not consensus or not conflict_report:
        raise RuntimeError("未获得任何科室分析结果")

    analysis_summary = agent.coordinator.summarize_analysis(
        all_responses,
        consensus,
        conflict_report,
    )
    analysis_summary["task_assignments"] = state.get("task_assignments", {}) or {}
    analysis_summary["dept_handoffs"] = {
        dept: resp.handoff_to_main if hasattr(resp, "handoff_to_main") else {}
        for dept, resp in all_responses.items()
    }
    analysis_summary["react_rounds"] = state.get("react_rounds", []) or []
    analysis_summary["graph_guidance"] = state.get("graph_guidance", {}) or {}
    analysis_summary["patient_profile"] = agent.patient_profile
    analysis_summary["clinical_prior"] = agent.clinical_prior
    analysis_summary["data_quality_issues"] = state.get("data_quality_issues", []) or []
    analysis_summary["quarantined_indicators"] = state.get("quarantined_indicators", []) or []
    analysis_summary["reasoning_labs"] = state.get("reasoning_labs", {}) or {}
    analysis_summary["recommended_departments"] = (
        (state.get("graph_guidance", {}) or {}).get("recommended_agents")
        or analysis_summary.get("supporting_departments", [])
    )
    analysis_summary["final_diagnosis"] = consensus.primary_diagnosis
    analysis_summary["final_recommendations"] = consensus.recommended_actions
    analysis_summary["stop_reason"] = state.get("stop_reason", "")

    agent.session_state["analysis_results"].append(analysis_summary)
    agent.logger.info("【分析完成】诊断：%s", consensus.primary_diagnosis)

    return {
        "analysis_summary": analysis_summary,
        "final_diagnosis": consensus.primary_diagnosis,
        "final_recommendations": consensus.recommended_actions,
    }
