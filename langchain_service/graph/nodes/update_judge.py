from typing import Any, Dict


def update_judge(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    all_responses = state.get("all_responses", {}) or {}
    round_responses = state.get("round_responses", {}) or {}
    consensus = state.get("consensus")
    conflict_report = state.get("conflict_report")

    weight_updates: Dict[str, float] = {}
    if all_responses and consensus:
        weight_updates = agent.coordinator.apply_feedback_and_update_weights(
            round_responses or all_responses,
            consensus,
            conflict_report.level,
        )

    round_observation = {
        "department_feedback_count": len(round_responses),
        "conflict_level": conflict_report.level.value if conflict_report else "unknown",
        "followup_questions": (state.get("non_department_observation", {}) or {}).get("followup_questions", []),
        "recommended_tests": (state.get("non_department_observation", {}) or {}).get("recommended_tests", []),
        "knowledge_snippets": (state.get("non_department_observation", {}) or {}).get("knowledge", []),
    }

    react_rounds = list(state.get("react_rounds", []) or [])
    react_rounds.append(
        {
            "round": state.get("current_round", 1),
            "thought": state.get("current_thought", ""),
            "actions": state.get("current_actions", []) or [],
            "selected_departments": state.get("selected_departments", []) or [],
            "action_reason": state.get("action_reason", ""),
            "observation": round_observation,
            "consensus": {
                "primary_diagnosis": consensus.primary_diagnosis if consensus else "未确定",
                "confidence": float(consensus.confidence) if consensus else 0.0,
                "conflict_level": conflict_report.level.value if conflict_report else "unknown",
            },
        }
    )

    remaining_departments = [
        dept
        for dept in agent.dept_agents.keys()
        if dept not in set(state.get("used_departments", []) or [])
    ]

    stop, stop_reason = agent._should_early_stop(
        round_no=state.get("current_round", 1),
        max_rounds=state.get("max_rounds", 5),
        consensus=consensus,
        conflict_report=conflict_report,
        missing_tests=state.get("missing_tests", []) or [],
        followup_questions=state.get("followup_questions", []) or [],
        remaining_departments=remaining_departments,
    )
    agent.logger.info("[REASONING][主Agent] 收敛判定=%s | 原因=%s", stop, stop_reason)

    next_round = state.get("current_round", 1)
    if not stop:
        next_round += 1

    return {
        "weight_updates": weight_updates,
        "department_weight_history": agent.weight_updater.get_weights(),
        "react_rounds": react_rounds,
        "should_stop": stop,
        "stop_reason": stop_reason,
        "current_round": next_round,
    }
