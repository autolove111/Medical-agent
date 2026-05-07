from typing import Any, Dict, Optional, Tuple

from .reference import get_reference_range

_REF_CODE_ALIAS = {
    "Hb": "HB",
    "PO4": "P",
}


def resolve_reference_bounds(
    indicator: str,
    patient_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], Optional[float]]:
    patient_profile = patient_profile or {}
    code = _REF_CODE_ALIAS.get(indicator, indicator)
    ref = get_reference_range(code)
    if not ref:
        return None, None

    gender_raw = str(patient_profile.get("gender", "") or "").strip().lower()
    if ("女" in gender_raw) or gender_raw.startswith("f"):
        gender_candidates = [ref.get("female"), ref.get("male")]
    elif ("男" in gender_raw) or gender_raw.startswith("m"):
        gender_candidates = [ref.get("male"), ref.get("female")]
    else:
        gender_candidates = [ref.get("male"), ref.get("female")]

    age_years = float(patient_profile.get("age_years", -1) or -1)
    if 0 <= age_years <= 14:
        range_candidates = [ref.get("pediatric"), ref.get("child"), *gender_candidates, ref.get("adult"), ref.get("normal")]
    elif 15 <= age_years <= 18:
        range_candidates = [ref.get("adolescent"), ref.get("teen"), *gender_candidates, ref.get("adult"), ref.get("normal")]
    elif age_years >= 65:
        range_candidates = [ref.get("elderly"), ref.get("geriatric"), *gender_candidates, ref.get("adult"), ref.get("normal")]
    else:
        range_candidates = [*gender_candidates, ref.get("adult"), ref.get("normal")]

    for rr in range_candidates:
        if not isinstance(rr, dict):
            continue
        low = rr.get("min")
        high = rr.get("max")
        if low is not None or high is not None:
            return low, high
    return None, None


def calculate_anomaly(
    indicator: str,
    value: float,
    patient_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    low, high = resolve_reference_bounds(indicator, patient_profile)

    severity = 0
    direction = "normal"
    if low is not None and value < low:
        direction = "low"
        if low <= 0:
            severity = 1
        else:
            ratio = (low - value) / low
            severity = 1 if ratio <= 0.15 else 2 if ratio <= 0.35 else 3
    elif high is not None and value > high:
        direction = "high"
        if high <= 0:
            severity = 1
        else:
            ratio = (value - high) / high
            severity = 1 if ratio <= 0.15 else 2 if ratio <= 0.35 else 3

    return {
        "value": value,
        "low": low,
        "high": high,
        "direction": direction,
        "severity": severity,
        "is_abnormal": severity > 0,
    }


def build_abnormal_bundle(
    lab_results: Dict[str, float],
    patient_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    abnormal_bundle: Dict[str, Dict[str, Any]] = {}
    for indicator, raw_value in (lab_results or {}).items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        abnormal_bundle[indicator] = calculate_anomaly(indicator, value, patient_profile)
    return abnormal_bundle


__all__ = ["build_abnormal_bundle", "calculate_anomaly", "resolve_reference_bounds"]
