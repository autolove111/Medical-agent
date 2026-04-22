"""兼容入口：tools 逻辑已迁移到 knowledge.tools。"""

from knowledge.tools import (  # noqa: F401
    analyze_medical_image,
    classify_medical_report,
    get_current_user_id,
    query_medical_knowledge,
    query_user_age_profile,
    query_user_medical_history,
    recheck_medical_image,
    set_current_user_id,
    tools,
)
