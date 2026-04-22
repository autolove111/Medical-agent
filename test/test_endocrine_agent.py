import sys, os, types
# ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# Prepare lightweight import stubs so we can import package modules without executing
# langchain_service/__init__.py which pulls many top-level imports.
LANGCHAIN_PATH = os.path.join(PROJECT_ROOT, "langchain_service")
KNOWLEDGE_PATH = os.path.join(LANGCHAIN_PATH, "knowledge")

if 'langchain_service' not in sys.modules:
    pkg = types.ModuleType('langchain_service')
    pkg.__path__ = [LANGCHAIN_PATH]
    sys.modules['langchain_service'] = pkg

if 'knowledge' not in sys.modules:
    kpkg = types.ModuleType('knowledge')
    kpkg.__path__ = [KNOWLEDGE_PATH]
    sys.modules['knowledge'] = kpkg

# Provide a minimal core.config.settings stub required by agents
core_config = types.ModuleType('core.config')
class _Settings:
    DASHSCOPE_MODEL = 'test-model'
    DASHSCOPE_API_KEY = 'sk-test'
    DASHSCOPE_BASE_URL = 'http://localhost/'

core_config.settings = _Settings()
sys.modules['core.config'] = core_config
sys.modules['core'] = types.ModuleType('core')

# Provide minimal langchain stubs
if 'langchain_core' not in sys.modules:
    lc_pkg = types.ModuleType('langchain_core')
    lc_pkg.__path__ = []
    sys.modules['langchain_core'] = lc_pkg
if 'langchain_core.prompts' not in sys.modules:
    prompts_mod = types.ModuleType('langchain_core.prompts')
    class PromptTemplate:
        def __init__(self, template=None):
            self.template = template
    prompts_mod.PromptTemplate = PromptTemplate
    sys.modules['langchain_core.prompts'] = prompts_mod
if 'langchain_core.output_parsers' not in sys.modules:
    parsers_mod = types.ModuleType('langchain_core.output_parsers')
    class JsonOutputParser:
        def parse(self, text: str):
            return text
    parsers_mod.JsonOutputParser = JsonOutputParser
    sys.modules['langchain_core.output_parsers'] = parsers_mod
lc_chat = types.ModuleType('langchain_community.chat_models')
class ChatOpenAI:
    def __init__(self, model=None, openai_api_key=None, openai_api_base=None, temperature=0.3, max_tokens=1200):
        self.model = model
        self.openai_api_key = openai_api_key
        self.openai_api_base = openai_api_base
    def invoke(self, messages):
        raise Exception('ChatOpenAI.invoke not set')
lc_chat.ChatOpenAI = ChatOpenAI
sys.modules['langchain_community.chat_models'] = lc_chat

lc_msgs = types.ModuleType('langchain_core.messages')
class HumanMessage:
    def __init__(self, content):
        self.content = content
class SystemMessage:
    def __init__(self, content):
        self.content = content
lc_msgs.HumanMessage = HumanMessage
lc_msgs.SystemMessage = SystemMessage
sys.modules['langchain_core.messages'] = lc_msgs

# Prevent importing the real langchain_service.task package __init__ by pre-creating the package module
if 'langchain_service.task' not in sys.modules:
    task_pkg = types.ModuleType('langchain_service.task')
    task_pkg.__path__ = [os.path.join(LANGCHAIN_PATH, 'task')]
    sys.modules['langchain_service.task'] = task_pkg

# Provide a minimal stub for knowledge.tools to avoid importing external langchain integrations
if 'knowledge.tools' not in sys.modules:
    kt = types.ModuleType('knowledge.tools')
    def query_medical_knowledge(query, scope=None, department=None):
        return ("", [])
    def query_user_medical_history(user_id):
        return ""
    def set_current_user_id(uid):
        return None
    kt.query_medical_knowledge = query_medical_knowledge
    kt.query_user_medical_history = query_user_medical_history
    kt.set_current_user_id = set_current_user_id
    sys.modules['knowledge.tools'] = kt

from langchain_service.task.lightweight_dept_agent import EndocrinologyAgent

class FakeResp:
    def __init__(self, content):
        self.content = content


def make_invoke_sequence():
    calls = {"i": 0}
    def invoke(messages):
        calls["i"] += 1
        if calls["i"] <= 2:
            raise Exception("simulated timeout")
        # third call: return a valid JSON string in content
        content = '{"primary_diagnosis": "糖尿病", "confidence": 0.92, "differential_diagnoses": [], "clinical_interpretation": "基于GLU>=11.1", "recommended_tests": ["HbA1c"], "recommended_departments": ["内分泌科"], "missing_indicators": []}'
        return FakeResp(content)
    return invoke


def run_test():
    agent = EndocrinologyAgent(use_llm=True)
    # replace llm.invoke with our sequence
    agent.llm.invoke = make_invoke_sequence()

    lab_results = {"GLU": 13.82}
    resp = agent.analyze(lab_results, gat_confidence=0.9, context={})

    print("HANDOFF:", resp.handoff_to_main if hasattr(resp, 'handoff_to_main') else None)
    print("PRIMARY DIAGNOSIS:", resp.primary_diagnosis.diagnosis, resp.primary_diagnosis.confidence)

if __name__ == '__main__':
    run_test()
