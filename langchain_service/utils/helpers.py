from typing import Any, Iterable, List, Optional


def dedupe_preserve_order(values: Iterable[Any]) -> List[Any]:
    return list(dict.fromkeys(values))


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = ["dedupe_preserve_order", "safe_float"]
