from typing import Any, Dict


def decide_departments(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    current_round = int(state.get("current_round", 1) or 1)
    agent.session_state["current_round"] += 1
    agent.logger.info("\n【分析开始】第 %s 轮", current_round)

    all_responses = state.get("all_responses", {}) or {}
    missing_tests = agent._derive_missing_tests(state.get("reasoning_labs", {}), all_responses)
    followup_questions = agent._build_followup_questions(
        state.get("reasoning_labs", {}),
        state.get("consensus"),
    )
    if state.get("data_quality_issues"):
        followup_questions = list(
            dict.fromkeys(
                followup_questions + ["检测到疑似OCR识别异常，请确认化验单原始数值是否准确。"]
            )
        )

    thought, actions = agent._plan_next_actions(
        round_no=current_round,
        lab_results=state.get("reasoning_labs", {}),
        gat_confidence=state.get("department_activation_scores", {}),
        graph_guidance=state.get("graph_guidance", {}) or {},
        task_assignments=state.get("task_assignments", {}) or {},
        used_departments=set(state.get("used_departments", []) or []),
        consensus=state.get("consensus"),
        conflict_report=state.get("conflict_report"),
        missing_tests=missing_tests,
        followup_questions=followup_questions,
    )

    consult_action = next(
        (item for item in actions if item.get("type") == "consult_departments"),
        None,
    )
    selected_departments = consult_action.get("departments", []) if consult_action else []
    action_reason = consult_action.get("reason", "无可调用科室") if consult_action else "无可调用科室"

    agent.logger.info("[THOUGHT][主Agent] %s", thought)

    return {
        "missing_tests": missing_tests,
        "followup_questions": followup_questions,
        "current_thought": thought,
        "current_actions": actions,
        "selected_departments": selected_departments,
        "action_reason": action_reason,
    }
