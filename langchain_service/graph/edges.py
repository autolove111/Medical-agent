from typing import Any, Dict


def route_after_update(state: Dict[str, Any], runtime: Any = None) -> str:
    return "write_conclusion" if state.get("should_stop") else "screen_activate"


__all__ = ["route_after_update"]
