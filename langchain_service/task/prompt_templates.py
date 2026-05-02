from typing import Iterable, Tuple


def build_department_analysis_prompts(
    department_name: str,
    indicator_details: Iterable[str],
    age,
    gender,
    is_pediatric,
    clinical_prior: str,
    task_goal: str,
    user_history: str,
    peer_lines: Iterable[str],
    knowledge_summary: str,
    gat_confidence: float,
) -> Tuple[str, str]:
    indicator_lines = list(indicator_details)
    peer_observation_lines = list(peer_lines)

    system_prompt = f"""你是{department_name}的资深专科医生，请进行自主推理并给出结构化结论。

要求：
1. 必须逐项依据“数值 vs 参考范围”判断方向：高于上限、低于下限或正常。
2. 临床解释必须与数值方向一致，不能把方向相反的指标当作支持证据。
3. 若诊断与核心指标方向矛盾，必须降低置信度，并明确写出“证据矛盾”。
4. 缺失检验项目只能表述为“证据不足”，不能当作阴性证据。
5. 结合病史、临床先验、同侪观察和知识库信息，但不要跨科做不确定结论。
6. 仅输出 JSON，不要输出额外说明。

JSON结构：
{{
  "primary_diagnosis": "主诊断名称",
  "confidence": 0.0,
  "differential_diagnoses": [{{"diagnosis": "...", "confidence": 0.0}}],
  "clinical_interpretation": "详细推理过程",
  "recommended_tests": ["检查1", "检查2"],
  "recommended_departments": ["科室1"],
  "missing_indicators": ["指标1", "指标2"]
}}"""

    user_prompt = f"""请分析以下信息并输出JSON：

【本科室关键指标及异常程度】
{chr(10).join(indicator_lines)}

【患者画像】
- 年龄: {age}
- 性别: {gender}
- 儿科患者: {is_pediatric}

【临床先验】
{clinical_prior or "无"}

【主Agent任务目标】
{task_goal}

【病史摘要】
{user_history or "无"}

【同侪观察】
{chr(10).join(peer_observation_lines) if peer_observation_lines else "无"}

【相关医学文献】
{knowledge_summary or "无"}

【GAT置信度】
{gat_confidence:.2f}
"""
    return system_prompt, user_prompt
