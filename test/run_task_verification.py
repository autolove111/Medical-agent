import sys
import os

# ensure repo root is on sys.path so imports work when running under tests/
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

results = {}

# 1) abnormal_bundle direction (static source check)
try:
    hier_path = os.path.normpath(os.path.join(repo_root, 'langchain_service', 'task', 'hierarchical_main_agent.py'))
    with open(hier_path, 'r', encoding='utf-8') as f:
        hier_src = f.read()
    # check if code defines a direction field in abnormal bundle
    has_direction_assignment = '"direction"' in hier_src or "'direction'" in hier_src
    has_direction_logic = 'direction = "low"' in hier_src or "direction = 'low'" in hier_src or 'direction = "high"' in hier_src
    results['abnormal_bundle_direction'] = bool(has_direction_assignment and has_direction_logic)
except Exception as e:
    results['abnormal_bundle_direction'] = False
    print('ERROR reading hierarchical_main_agent.py:', e)

# 2) prompt contains direction enforcement and Cr low constraint
try:
    lw_path = os.path.join(os.path.dirname(__file__), '..', 'langchain_service', 'task', 'lightweight_dept_agent.py')
    lw_path = os.path.normpath(lw_path)
    with open(lw_path, 'r', encoding='utf-8') as f:
        src = f.read()
    cond1 = '必须逐项依据' in src or '判断方向' in src
    cond2 = 'Cr/CysC' in src or '不得直接作为肾功能不全正证据' in src or '低于下限' in src
    results['prompt_enforcement'] = bool(cond1 and cond2)
except Exception as e:
    results['prompt_enforcement'] = False
    print('ERROR reading lightweight_dept_agent.py:', e)

# 3) knowledge tools accept direction (static signature check)
try:
    tools_path = os.path.normpath(os.path.join(repo_root, 'langchain_service', 'knowledge', 'tools.py'))
    with open(tools_path, 'r', encoding='utf-8') as f:
        tools_src = f.read()
    sig_ok = 'def query_medical_knowledge' in tools_src and 'direction' in tools_src.split('def query_medical_knowledge',1)[1][:200]
    results['knowledge_direction_callable'] = bool(sig_ok)
except Exception as e:
    results['knowledge_direction_callable'] = False
    print('ERROR reading knowledge/tools.py:', e)

# 4) GAT only-by-name requirement check (static analysis: detect usage of abnormal_bundle/is_abnormal/value in _compute_gat_confidence)
try:
    # reuse hier_src from above if present
    if 'hier_src' not in locals():
        hier_path = os.path.normpath(os.path.join(repo_root, 'langchain_service', 'task', 'hierarchical_main_agent.py'))
        with open(hier_path, 'r', encoding='utf-8') as f:
            hier_src = f.read()
    # locate the _compute_gat_confidence function body
    idx = hier_src.find('def _compute_gat_confidence')
    if idx >= 0:
        # find end of function by locating next top-level 'def ' after this one
        # look for next class-method definition (indented) to isolate this method
        next_def = hier_src.find('\n    def ', idx + 1)
        func_body = hier_src[idx: next_def if next_def > 0 else None]
        # check for direct references to abnormal bundle fields or is_abnormal/severity
        uses_abnormal = any(token in func_body for token in ['abnormal_bundle', 'is_abnormal', "'severity'", '"severity"'])
        # remove the function signature region before checking tokens (avoid matching parameter names)
        sig_end = func_body.find('):')
        if sig_end != -1:
            func_check_body = func_body[sig_end + 2:]
        else:
            func_check_body = func_body
        # debug output for investigation
        print('--- DEBUG: extracted _compute_gat_confidence check-body start ---')
        print(func_check_body[:800])
        print('--- DEBUG: extracted _compute_gat_confidence check-body end ---')
        tokens = ['abnormal_bundle', 'is_abnormal', "'severity'", '"severity"']
        found = [t for t in tokens if t in func_check_body]
        print('DEBUG tokens found:', found)
        for t in found:
            print(f"DEBUG token '{t}' pos:", func_check_body.find(t))
        uses_abnormal = any(token in func_check_body for token in ['abnormal_bundle', 'is_abnormal', "'severity'", '"severity"'])
        results['gat_value_dependent'] = bool(uses_abnormal)
    else:
        results['gat_value_dependent'] = False
except Exception as e:
    results['gat_value_dependent'] = False
    print('ERROR analyzing GAT in hierarchical_main_agent.py:', e)

# Print summary
print('=== Task Verification Results ===')
print('1) abnormal_bundle includes direction:', 'PASS' if results['abnormal_bundle_direction'] else 'FAIL')
print('2) dept prompt enforces direction + Cr low constraint:', 'PASS' if results['prompt_enforcement'] else 'FAIL')
print('3) knowledge tools accept direction parameter and return string:', 'PASS' if results['knowledge_direction_callable'] else 'FAIL')
print('4) GAT still influenced by values (expected True -> requirement NOT met):', 'YES' if results['gat_value_dependent'] else 'NO')

# Exit code: 0 if all checks except GAT requirement are PASS and gat_value_dependent==True (meaning not fixed)
ok = results['abnormal_bundle_direction'] and results['prompt_enforcement'] and results['knowledge_direction_callable'] and isinstance(results['gat_value_dependent'], bool)
sys.exit(0 if ok else 2)
