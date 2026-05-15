from typing import Optional

from agents import create_agent


def create_medical_agent(user_id: Optional[str] = None, agent_type: Optional[str] = None):
    return create_agent(agent_type=agent_type, user_id=user_id)
