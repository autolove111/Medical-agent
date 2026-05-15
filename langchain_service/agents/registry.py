from typing import Optional

from .general_agent import GeneralMedicalAgent

AVAILABLE_AGENT_TYPES = ["general"]


def normalize_agent_type(agent_type: Optional[str]) -> str:
    _ = agent_type
    return "general"


def create_agent(agent_type: Optional[str] = None, user_id: Optional[str] = None) -> GeneralMedicalAgent:
    _ = agent_type
    return GeneralMedicalAgent(user_id=user_id)
