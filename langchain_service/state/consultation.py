from typing import Any, Dict, List, Optional, TypedDict


class ConsultationState(TypedDict, total=False):
    lab_results: Dict[str, float]
    max_rounds: int
    patient_profile: Dict[str, Any]
    clinical_prior: str
    report_image: Optional[bytes]
    patient_id: Optional[str]

    user_history_text: str
    data_quality_issues: List[str]
    quarantined_indicators: List[str]
    reasoning_labs: Dict[str, float]
    abnormal_bundle: Dict[str, Dict[str, Any]]

    key_indicators: List[str]
    graph_guidance: Dict[str, Any]
    department_activation_scores: Dict[str, float]
    task_assignments: Dict[str, Dict[str, Any]]

    current_round: int
    current_thought: str
    current_actions: List[Dict[str, Any]]
    selected_departments: List[str]
    action_reason: str
    missing_tests: List[str]
    followup_questions: List[str]
    non_department_observation: Dict[str, Any]

    round_responses: Dict[str, Any]
    all_responses: Dict[str, Any]
    used_departments: List[str]
    conflict_report: Any
    consensus: Any
    weight_updates: Dict[str, float]
    department_weight_history: Dict[str, float]

    react_rounds: List[Dict[str, Any]]
    should_stop: bool
    stop_reason: str
    analysis_summary: Dict[str, Any]
    final_diagnosis: str
    final_recommendations: List[str]


def create_initial_consultation_state(
    lab_results: Dict[str, float],
    max_rounds: int = 5,
    patient_profile: Optional[Dict[str, Any]] = None,
    clinical_prior: str = "",
    report_image: Optional[bytes] = None,
    patient_id: Optional[str] = None,
) -> ConsultationState:
    return ConsultationState(
        lab_results=lab_results,
        max_rounds=max_rounds,
        patient_profile=patient_profile or {},
        clinical_prior=clinical_prior or "",
        report_image=report_image,
        patient_id=patient_id,
    )
