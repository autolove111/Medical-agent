from typing import Any, Dict, List


def screen_activate(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    reasoning_labs = state.get("reasoning_labs", {})
    abnormal_bundle = agent._compute_abnormal_bundle(reasoning_labs)

    key_indicators: List[str] = []
    indicator_weights: Dict[str, float] = {}
    graph_labs = reasoning_labs
    recommended_agents: List[str] = []
    agent_weights: Dict[str, float] = {}
    collaboration_notes: List[str] = []

    try:
        from graph.graph_inference import get_graph_models

        indicator_gat, expert_gat = get_graph_models()
        graph_nodes = (
            set(getattr(indicator_gat, "graph", {}).nodes())
            if getattr(indicator_gat, "graph", None) is not None
            else set()
        )
        graph_labs = {
            key: value
            for key, value in reasoning_labs.items()
            if not graph_nodes or key in graph_nodes
        }
        if not graph_labs:
            raise ValueError("no matched graph indicators")

        indicator_result = indicator_gat.forward(graph_labs)
        key_indicators = indicator_result.get("key_indicators", []) or []
        indicator_weights = indicator_result.get("weights", {}) or {}

        expert_result = expert_gat.forward(key_indicators, indicator_weights)
        recommended_agents = expert_result.get("recommended_agents", []) or []
        agent_weights = expert_result.get("agent_weights", {}) or {}
        collaboration_notes = expert_result.get("collaboration_notes", []) or []
    except Exception as exc:
        agent.logger.warning("图推理降级为启发式筛选: %s", exc)

    if not key_indicators:
        key_indicators = [
            key
            for key in graph_labs.keys()
            if bool((abnormal_bundle.get(key) or {}).get("is_abnormal"))
        ][:5]

    if not indicator_weights:
        indicator_weights = {key: 0.5 for key in key_indicators}

    gat_confidence = agent._compute_gat_confidence(reasoning_labs, abnormal_bundle)
    department_activation_scores: Dict[str, float] = {}
    for dept in agent.dept_agents.keys():
        department_activation_scores[dept] = round(
            float(gat_confidence.get(dept, 0.0)) * 0.7
            + float(agent_weights.get(dept, 0.0)) * 0.3,
            4,
        )

    graph_guidance = {
        "key_indicators": key_indicators,
        "indicator_weights": indicator_weights,
        "recommended_agents": recommended_agents,
        "agent_weights": agent_weights,
        "collaboration_notes": collaboration_notes,
    }

    task_assignments = agent._build_task_assignments(
        reasoning_labs,
        gat_confidence,
        state.get("current_round", 1),
        abnormal_bundle,
        state.get("user_history_text", ""),
    )

    agent.logger.info(
        "[THOUGHT][主Agent] 关键指标=%s | 推荐科室=%s",
        key_indicators,
        recommended_agents,
    )

    return {
        "abnormal_bundle": abnormal_bundle,
        "key_indicators": key_indicators,
        "graph_guidance": graph_guidance,
        "department_activation_scores": department_activation_scores,
        "task_assignments": task_assignments,
    }
