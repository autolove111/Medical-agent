import sys, os
# ensure project root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from langchain_service.knowledge.tools import query_medical_knowledge

cases = [
    ("GLU", "high", "内分泌科"),
    ("ALT", "high", "感染科"),
    ("Cr", "low", "肾内科"),
]

for ind, direction, dept in cases:
    print("=== QUERY", ind, "direction=", direction, "dept=", dept)
    try:
        res = query_medical_knowledge(keyword=ind, scope="department", department=dept, indicator=ind, direction=direction)
        print(str(res)[:2000])
    except Exception as e:
        print("ERROR:", e)
    print('\n')
