from typing import Any, Dict


def build_consensus(state: Dict[str, Any], runtime: Any) -> Dict[str, Any]:
    agent = runtime.agent
    all_responses = state.get("all_responses", {}) or {}
    conflict_report = state.get("conflict_report")

    consensus = None
    if all_responses:
        conflict_level = conflict_report.level if conflict_report else None
        consensus = agent._weighted_consensus(all_responses, conflict_level)
        agent.logger.info(
            "[REASONING][主Agent] 共识推理: 主诊断=%s, 置信度=%.2f, 支持科室=%s, 冲突科室=%s",
            consensus.primary_diagnosis,
            consensus.confidence,
            consensus.supporting_depts,
            consensus.conflicting_depts,
        )

    return {"consensus": consensus}
