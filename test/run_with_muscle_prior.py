import asyncio
import sys
import os

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from langchain_service.task.hierarchical_main_agent import HierarchicalMedicalAgent

async def main():
    lab_results = {
        'a_g_ratio': 1.72,
        'alp': 69.6,
        'alt': 48.2,
        'ast': 40.8,
        'calcium': 2.19,
        'chloride': 102.0,
        'cholinesterase': 5.51,
        'co2': 22.4,
        'creatine_kinase': 73.7,
        'creatinine': 28.5,
        'cystatin_c': 0.49,
        'ggt': 64.88,
        'glucose': 13.82,
        'ldh': 184.06,
        'phosphorus': 0.95,
        'potassium': 4.37,
        'sodium': 135.0,
        'total_bile_acid': 10.0,
        'urea': 3.17,
        'uric_acid': 159.3,
    }

    agent = HierarchicalMedicalAgent(user_id='3cf1f094-3bd7-41da-abec-201110fcb90e')
    # empty patient_profile, set clinical_prior to muscle injury
    result = await agent.analyze_lab_results(lab_results, max_rounds=3, patient_profile={}, clinical_prior='肌损伤')

    print('\n=== Analysis Summary Keys ===')
    for k in sorted(result.keys()):
        print('-', k)

    print('\n=== Consensus ===')
    print(result.get('primary_diagnosis', result.get('consensus', 'N/A')))

    print('\n=== React Rounds ===')
    for r in result.get('react_rounds', []):
        print(f"Round {r.get('round')}: selected_departments={r.get('selected_departments')}, consensus={r.get('consensus')}")

    print('\n=== Dept Handoffs ===')
    for dept, h in (result.get('dept_handoffs') or {}).items():
        print(f"{dept}: {h}")

    print('\n=== Task Assignments (brief) ===')
    ta = result.get('task_assignments', {})
    for dept, info in ta.items():
        print(f"{dept}: gate_confidence={info.get('gate_confidence')}, focus_indicators={info.get('focus_indicators')}\n")

if __name__ == '__main__':
    asyncio.run(main())
