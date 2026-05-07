from typing import Any, Dict


async def parallel_consult(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    actions = state.get("current_actions", []) or []
    non_department_observation = agent._execute_non_department_actions(actions)

    selected_departments = state.get("selected_departments", []) or []
    all_responses = dict(state.get("all_responses", {}) or {})
    round_responses: Dict[str, Any] = {}
    conflict_report = state.get("conflict_report")
    used_departments = list(state.get("used_departments", []) or [])

    if selected_departments:
        agent.logger.info(
            "[ACTION][主Agent] 本轮调用科室=%s | 原因=%s",
            selected_departments,
            state.get("action_reason", ""),
        )
        round_responses, conflict_report = await agent.coordinator.analyze_in_parallel(
            state.get("reasoning_labs", {}),
            gat_confidence_scores=state.get("department_activation_scores", {}),
            user_id=agent.user_id,
            context={
                "need_user_history": True,
                "round": state.get("current_round", 1),
                "main_goal": "判断患者最可能患病并形成可解释结论",
                "reasoning_focus": "疾病收敛 + 鉴别排除",
                "task_assignments": state.get("task_assignments", {}) or {},
                "peer_handoffs": {
                    dept: resp.handoff_to_main if hasattr(resp, "handoff_to_main") else {}
                    for dept, resp in all_responses.items()
                },
            },
            selected_departments=selected_departments,
        )
        all_responses.update(round_responses)
        used_departments = list(dict.fromkeys(used_departments + selected_departments))

    if not conflict_report:
        conflict_report = agent.coordinator._detect_conflicts(all_responses)

    return {
        "non_department_observation": non_department_observation,
        "round_responses": round_responses,
        "all_responses": all_responses,
        "used_departments": used_departments,
        "conflict_report": conflict_report,
    }
