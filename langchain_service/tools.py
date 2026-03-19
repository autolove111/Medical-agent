from langchain.tools import Tool
from typing import Optional
import logging
import requests
from contextvars import ContextVar  # 【修复】使用 ContextVar 替代全局变量，实现请求级别隔离
from sqlalchemy import create_engine, text
from config import settings

logger = logging.getLogger(__name__)

# 【修复】使用 ContextVar 代替全局变量
# 这样即使有多个用户同时发送请求，每个请求都有自己独立的 user_id 上下文
# 避免并发冲突导致用户数据泄露
_current_user_id: ContextVar[Optional[str]] = ContextVar('current_user_id', default=None)

def set_current_user_id(user_id: Optional[str]):
    """设置当前请求的 user_id（线程/任务安全）"""
    _current_user_id.set(user_id)

def get_current_user_id() -> Optional[str]:
    """获取当前请求的 user_id（线程/任务安全）"""
    return _current_user_id.get()

# 连接医学知识库
try:
    engine = create_engine(settings.DATABASE_URL)
except Exception as e:
    logger.warning(f"数据库连接失败: {e}")
    engine = None

def query_medical_knowledge(keyword: str) -> str:
    """
    查询医学知识库（使用 FAISS 向量库）
    
    【修复】改为使用 RAG 系统的 FAISS 索引，而不是数据库查询
    这样可以利用语义相似度匹配，更好地找到相关医学文档
    """
    try:
        # 延迟导入以避免循环依赖
        from rag import retrieve_medical_knowledge as retrieve_via_rag
        
        # 使用 FAISS 进行向量相似度检索
        result, sources = retrieve_via_rag(keyword)
        
        # 格式化输出
        if result.strip():
            return result
        else:
            return f"【知识库检索结果】未找到关键词 '{keyword}' 的相关医学文献"
            
    except Exception as e:
        logger.error(f"RAG 检索异常: {e}")
        return f"【检索异常】{str(e)}"

def query_user_medical_history(user_id: Optional[str]) -> str:
    """通过后端内部接口查询用户医学历史（调用后端，由后端再走 repository 实现）。

    输入：user_id（字符串形式的 UUID）
    
    【重要修复】优先级：
    1. 如果 user_id 是有效的 UUID 格式，直接使用它
    2. 否则，从全局上下文 get_current_user_id() 获取真实的 user_id
    3. 如果都没有，返回错误
    """
    # 判断传入的 user_id 是否为有效 UUID（通过检查长度和格式）
    is_valid_uuid = (
        user_id and 
        isinstance(user_id, str) and 
        len(user_id) == 36 and  # UUID 标准长度
        user_id.count('-') == 4 and  # UUID 中 - 的个数
        user_id != "当前用户" and  # 排除中文字符串
        user_id != "无用户ID"
    )
    
    # 【关键修复】优先使用从全局上下文获取的 user_id（这是真实的 UUID）
    # 只有在全局上下文为空时，才考虑使用传入的 user_id 参数
    effective_user_id = get_current_user_id() or (user_id if is_valid_uuid else None)
    
    if not effective_user_id:
        return "【用户信息】当前为匿名访问模式，无法查询用户既往史。建议登录后重试以获取个性化建议。"

    backend = getattr(settings, "BACKEND_URL", "http://localhost:8080")
    try:
        url = f"{backend}/api/v1/internal/user/medical-history"
        resp = requests.get(url, params={"userId": effective_user_id}, timeout=5)
        if resp.status_code != 200:
            logger.error(f"后端返回非200: {resp.status_code} {resp.text}")
            return f"【后端错误】查询病历失败: {resp.status_code}"
        j = resp.json()
        if j.get("status") == "success":
            med_history = j.get('medicalHistory', '无')
            drug_allergy = j.get('drugAllergy', '无')
            return f"【既往史】{med_history}\n【过敏信息】{drug_allergy}"
        else:
            return f"【后端错误】{j.get('message','未知错误')}"
    except Exception as e:
        logger.error(f"查询用户病历异常: {e}")
        return f"【系统异常】无法查询病历: {str(e)}"

def classify_medical_report(content: str) -> str:
    """分类医疗报告"""
    keywords_map = {
        "血液": "血液检查",
        "CBC": "血液检查",
        "肝功": "肝功能检查",
        "Liver": "肝功能检查",
        "肾功": "肾功能检查",
        "Kidney": "肾功能检查",
        "血糖": "代谢检查",
        "葡萄糖": "代谢检查",
        "心电": "心脏检查",
        "ECG": "心脏检查",
        "尿": "尿液检查",
        "Urine": "尿液检查",
    }
    
    for keyword, classification in keywords_map.items():
        if keyword in content:
            return classification
    
    return "综合医学报告"

# 定义 LangChain Tool
tools = [
    Tool(
        name="QueryMedicalKnowledge",
        func=query_medical_knowledge,
        description="从医学知识库查询相关医学信息。输入：医学关键词（如血红蛋白、糖尿病、高血压、头痛、头疼等）"
    ),
    Tool(
        name="QueryUserHistory",
        func=query_user_medical_history,
        description="""查询当前用户的既往史、过敏信息。
        传入用户 ID（格式为 UUID）。
        注意：不要传入中文文本如'当前用户'或'无用户ID'，必须是有效的 UUID 字符串。
        如果没有用户 ID，该工具会返回错误。"""
    ),
    Tool(
        name="ClassifyReport",
        func=classify_medical_report,
        description="自动分类医疗报告类型。输入：报告内容"
    ),
]
