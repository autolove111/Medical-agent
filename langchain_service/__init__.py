# MedLabAgent LangChain Service - 根目录导入转发层
# 这个文件确保向后兼容性：旧的导入语句如 `from agent_streaming import ...` 仍然可以工作

# 核心模块
from core.config import settings
from core.agent_streaming import create_medical_agent

# 知识库模块
from knowledge.medical_knowledge import *
from knowledge.reference_ranges import *
from knowledge.shared_knowledge_retriever import *
from knowledge.rag import RAGSystem
from knowledge.department_knowledge_base import *
from knowledge.department_tools import *
from knowledge.department_collaboration_graph import *

# 图结构模块
from graph.graph_state import *
from graph.graph_utils import *
from graph.graph_inference import *

# 任务路由模块
from task.task_router import *
from task.dept_coordinator import *
from task.dept_agent_response import *
from task.hierarchical_main_agent import *
from task.lightweight_dept_agent import *

# 视觉分析模块
from vision.vision_analyzer import *

# 实验模块
from experimental.gat_react_agent import *
from experimental.gat_react_diagnosis_engine import *
from experimental.expert_gat import *
from experimental.indicator_gat import *
from experimental.react_constraint_engine import *
from experimental.final_validation import *

# 工具模块
from utils.weight_updater import *
from utils.diagnose import *

__all__ = [
    # Core
    "settings", "create_medical_agent",
    # Knowledge
    "RAGSystem",
    # Other imports...
]
