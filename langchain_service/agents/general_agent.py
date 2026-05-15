from typing import Dict

from .base_agent import BaseMedicalAgent


def build_general_memory(history_text: str, lab_results: Dict[str, float], query: str) -> str:
    parts = []
    if history_text:
        parts.append(history_text)
    if lab_results:
        parts.append(
            "Relevant labs:\n" + "\n".join(f"- {key}: {value}" for key, value in sorted(lab_results.items()))
        )
    if query:
        parts.append("Current request:\n" + query)
    return "\n\n".join(parts) if parts else "No prior memory."


class GeneralMedicalAgent(BaseMedicalAgent):
    agent_type = "general"
    agent_label = "General Medical Agent"
    department_name = None
    specialty_prompt = (
        "You are the general medical agent. Answer broadly, summarize evidence, "
        "and avoid pretending to be a multi-agent coordinator."
    )

    def build_memory_context(self, history_text: str, lab_results: Dict[str, float], query: str) -> str:
        return build_general_memory(history_text, lab_results, query)
