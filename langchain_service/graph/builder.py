from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph

from graph.edges import route_after_update
from graph.nodes import (
    build_consensus,
    decide_departments,
    parallel_consult,
    parse_report,
    screen_activate,
    update_judge,
    write_conclusion,
)
from state.consultation import ConsultationState, create_initial_consultation_state


class ConsultationWorkflowRuntime:
    def __init__(self, agent: Any):
        self.agent = agent
        self.graph = self._compile_graph()

    def _compile_graph(self):
        workflow = StateGraph(ConsultationState)
        workflow.add_node("parse_report", lambda state: parse_report(state, self))
        workflow.add_node("screen_activate", lambda state: screen_activate(state, self))
        workflow.add_node("decide_departments", lambda state: decide_departments(state, self))
        workflow.add_node("parallel_consult", lambda state: parallel_consult(state, self))
        workflow.add_node("consensus", lambda state: build_consensus(state, self))
        workflow.add_node("update_judge", lambda state: update_judge(state, self))
        workflow.add_node("write_conclusion", lambda state: write_conclusion(state, self))

        workflow.set_entry_point("parse_report")
        workflow.add_edge("parse_report", "screen_activate")
        workflow.add_edge("screen_activate", "decide_departments")
        workflow.add_edge("decide_departments", "parallel_consult")
        workflow.add_edge("parallel_consult", "consensus")
        workflow.add_edge("consensus", "update_judge")
        workflow.add_conditional_edges(
            "update_judge",
            lambda state: route_after_update(state, self),
            {
                "screen_activate": "screen_activate",
                "write_conclusion": "write_conclusion",
            },
        )
        workflow.add_edge("write_conclusion", END)
        return workflow.compile()

    async def run(
        self,
        lab_results: Dict[str, float],
        max_rounds: int = 5,
        patient_profile: Optional[Dict[str, Any]] = None,
        clinical_prior: str = "",
        report_image: bytes | None = None,
        patient_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        initial_state = create_initial_consultation_state(
            lab_results=lab_results,
            max_rounds=max_rounds,
            patient_profile=patient_profile,
            clinical_prior=clinical_prior,
            report_image=report_image,
            patient_id=patient_id,
        )
        result = await self.graph.ainvoke(initial_state)
        return result["analysis_summary"]


def build_consultation_graph(agent: Any):
    return ConsultationWorkflowRuntime(agent)


async def run_consultation_workflow(
    agent: Any,
    lab_results: Dict[str, float],
    max_rounds: int = 5,
    patient_profile: Optional[Dict[str, Any]] = None,
    clinical_prior: str = "",
    report_image: bytes | None = None,
    patient_id: Optional[str] = None,
) -> Dict[str, Any]:
    runtime = build_consultation_graph(agent)
    return await runtime.run(
        lab_results=lab_results,
        max_rounds=max_rounds,
        patient_profile=patient_profile,
        clinical_prior=clinical_prior,
        report_image=report_image,
        patient_id=patient_id,
    )


__all__ = [
    "ConsultationWorkflowRuntime",
    "build_consultation_graph",
    "run_consultation_workflow",
]
