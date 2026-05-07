"""
==============================================
【模块全称】Knowledge 模块完整链路测试套件
【核心定位】独立的综合测试工具，逐个测试 Knowledge 的所有 13 条链路
【测试范围】
  1. 嵌入模型创建 (embedding_FAISS.create_embeddings)
  2. 向量库加载 (embedding_FAISS.load_vectorstore_from_dir)
  3. 向量库构建 (embedding_FAISS.build_main_vectorstore)
  4. 向量相似度检索 (vectorstore.similarity_search_with_score)
  5. 查询标准化 (rag_query.build_query_context)
  6. Redis 缓存 (rag_cache.RAGCache)
  7. 结果格式化 (rag_formatter.format_documents_as_answer)
  8. 参考值查询 (reference_ranges.get_reference_range)
  9. 文本清洁 (text_cleaner.clean_documents)
 10. 文本分块 (chunk_strategies.split_documents)
 11. 文档加载 (document_loaders.load_text_documents)
 12. 知识图谱增强 (rag_graph.GraphContextRetriever)
 13. 完整 RAG 流程 (rag.RAGSystem.retrieve)
【使用场景】
 - 开发测试：验证 Knowledge 模块各组件是否正常
 - 调试排查：精确定位哪个链路出现问题
 - CI/CD 集成：自动化测试所有链路
【特性】
 - 独立的测试函数，可单独运行
 - 详细的错误信息和诊断建议
 - 彩色输出便于快速识别
 - 测试报告生成
==============================================
"""

import os
import sys
import json
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# ===== 路径配置 =====
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(CURRENT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ===== 颜色输出配置 =====
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(msg: str):
    """打印测试头部"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")


def print_test_start(test_name: str, test_num: int):
    """打印测试开始"""
    print(f"{Colors.BOLD}{Colors.BLUE}[{test_num}] 开始测试: {test_name}{Colors.RESET}")


def print_success(msg: str):
    """打印成功信息"""
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")


def print_error(msg: str):
    """打印错误信息"""
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")


def print_warning(msg: str):
    """打印警告信息"""
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")


def print_info(msg: str):
    """打印信息"""
    print(f"{Colors.WHITE}{msg}{Colors.RESET}")


def print_diagnostic(msg: str):
    """打印诊断建议"""
    print(f"{Colors.CYAN}💡 诊断: {msg}{Colors.RESET}")


# ===== 全局测试状态 =====
test_results: List[Dict] = []


def record_test_result(test_name: str, test_num: int, passed: bool, error_msg: str = "", diagnostic: str = ""):
    """记录测试结果"""
    test_results.append({
        "test_num": test_num,
        "test_name": test_name,
        "passed": passed,
        "error_msg": error_msg,
        "diagnostic": diagnostic,
        "timestamp": datetime.now().isoformat()
    })


# ==============================================
# 【测试 1】嵌入模型创建
# ==============================================
def test_1_create_embeddings():
    """【第一阶段】测试：创建向量嵌入模型（支持本地/API双模式）"""
    test_name = "[1️⃣ 基础] 嵌入模型创建 (embedding_FAISS.create_embeddings)"
    test_num = 1
    print_test_start(test_name, test_num)
    
    try:
        from core.config import settings
        from knowledge.embedding_FAISS import create_embeddings
        
        print_info(f"使用本地嵌入路径: {settings.RAG_LOCAL_EMBEDDING_PATH}")
        embeddings = create_embeddings(purpose="rag")
        
        if embeddings is None:
            print_error("create_embeddings() 返回 None")
            record_test_result(test_name, test_num, False, "返回 None")
            return False
        
        # 测试嵌入函数
        test_text = ["测试文本"]
        result = embeddings.embed_documents(test_text)
        if not result or len(result) == 0:
            print_error("嵌入文本失败")
            record_test_result(test_name, test_num, False, "嵌入失败")
            return False
        
        vector_dim = len(result[0])
        print_success(f"嵌入模型创建成功 (维度: {vector_dim})")
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查网络连接、API 密钥有效性、DashScope API 可用性")
        record_test_result(test_name, test_num, False, error_msg, "检查网络和 API 配置")
        return False


# ==============================================
# 【测试 2】向量库加载
# ==============================================
def test_2_load_vectorstore():
    """【第一阶段】测试：从本地加载向量库"""
    test_name = "[1️⃣ 基础] 向量库加载 (embedding_FAISS.load_vectorstore_from_dir)"
    test_num = 2
    print_test_start(test_name, test_num)
    
    try:
        from core.config import settings
        from knowledge.embedding_FAISS import create_embeddings, load_vectorstore_from_dir
        
        # 使用本地嵌入模型
        embeddings = create_embeddings(purpose="rag")
        
        # 查找向量库路径
        main_vectorstore_path = os.path.join(settings.VECTOR_DB_PATH, "main")
        if not os.path.exists(main_vectorstore_path):
            print_warning(f"向量库不存在: {main_vectorstore_path}")
            print_diagnostic("请先运行: python -m langchain_service.knowledge.build_vectorstore")
            record_test_result(test_name, test_num, False, "向量库文件不存在", "需要先构建向量库")
            return False
        
        vectorstore = load_vectorstore_from_dir(main_vectorstore_path, embeddings)
        if vectorstore is None:
            print_error("load_vectorstore_from_dir() 返回 None")
            record_test_result(test_name, test_num, False, "加载失败")
            return False
        
        # 尝试检索测试数据
        test_query = "测试"
        results = vectorstore.similarity_search(test_query, k=1)
        if results is None:
            print_error("向量库检索失败")
            record_test_result(test_name, test_num, False, "检索失败")
            return False
        
        print_success(f"向量库加载成功 (路径: {main_vectorstore_path})")
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查向量库文件完整性、FAISS 库版本兼容性")
        record_test_result(test_name, test_num, False, error_msg, "检查向量库和依赖")
        return False


# ==============================================
# 【测试 3】向量库构建
# ==============================================
def test_3_build_vectorstore():
    """【第三阶段】测试：从文档构建向量库"""
    test_name = "[3️⃣ 向量库] 向量库构建 (embedding_FAISS.build_main_vectorstore)"
    test_num = 6
    print_test_start(test_name, test_num)
    
    try:
        from core.config import settings
        from knowledge.embedding_FAISS import create_embeddings, build_main_vectorstore
        
        # 使用本地嵌入模型
        embeddings = create_embeddings(purpose="rag")
        
        # 构建向量库
        print_info("正在构建向量库，请稍候...")
        vectorstore = build_main_vectorstore(embeddings)
        
        if vectorstore is None:
            print_error("build_main_vectorstore() 返回 None")
            record_test_result(test_name, test_num, False, "构建失败")
            return False
        
        # 测试构建后的向量库
        test_results = vectorstore.similarity_search("测试", k=1)
        if not test_results:
            print_warning("向量库已构建但无检索结果（可能文档为空）")
            print_diagnostic("检查 main_agent_docs 和 dept_agent_docs 目录中是否有文档")
            record_test_result(test_name, test_num, False, "无检索结果", "检查文档文件")
            return False
        
        print_success("向量库构建成功")
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查文档文件、API 配额、临时空间大小")
        record_test_result(test_name, test_num, False, error_msg, "检查构建环境")
        return False


# ==============================================
# 【测试 4】向量相似度检索
# ==============================================
def test_4_similarity_search():
    """【第五阶段】测试：向量相似度检索（核心）"""
    test_name = "[5️⃣ 检索] 向量相似度检索 (similarity_search_with_score)"
    test_num = 9
    print_test_start(test_name, test_num)
    
    try:
        from core.config import settings
        from knowledge.embedding_FAISS import create_embeddings, load_vectorstore_from_dir, get_vectorstore_candidate_paths
        
        # 使用本地嵌入模型
        embeddings = create_embeddings(purpose="rag")
        
        # 查找向量库
        vectorstore = None
        for candidate in get_vectorstore_candidate_paths(scope="main"):
            vectorstore = load_vectorstore_from_dir(candidate, embeddings)
            if vectorstore:
                break
        
        if vectorstore is None:
            print_warning("未找到向量库")
            print_diagnostic("请先构建向量库: python -m langchain_service.knowledge.build_vectorstore")
            record_test_result(test_name, test_num, False, "向量库不存在", "需要构建向量库")
            return False
        
        # 执行相似度检索
        query = "肾脏"
        docs_with_scores = vectorstore.similarity_search_with_score(query, k=3)
        
        if not docs_with_scores:
            print_warning(f"查询 '{query}' 无结果")
            print_diagnostic("这可能是正常的（如果文档中没有相关内容）")
            record_test_result(test_name, test_num, False, "无检索结果", "尝试其他查询")
            return False
        
        # 显示检索结果
        print_success(f"检索成功，返回 {len(docs_with_scores)} 条结果:")
        for i, (doc, score) in enumerate(docs_with_scores, 1):
            source = doc.metadata.get("source", "unknown") if doc.metadata else "unknown"
            preview = doc.page_content[:100].replace('\n', ' ')
            print_info(f"  [{i}] 评分: {score:.6f} | 来源: {source}")
            print_info(f"      预览: {preview}...")
        
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查向量库完整性、FAISS 版本、嵌入模型")
        record_test_result(test_name, test_num, False, error_msg, "检查向量库和模型")
        return False


# ==============================================
# 【测试 5】查询标准化
# ==============================================
def test_5_query_context():
    """【第四阶段】测试：查询上下文标准化"""
    test_name = "[4️⃣ 查询] 查询标准化 (rag_query.build_query_context)"
    test_num = 7
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.rag_query import build_query_context
        
        # 测试各种输入
        test_cases = [
            ("肌酐升高", "main", None, "主库查询"),
            ("  白细胞异常  ", "main", None, "去除空格"),
            ("肌酐", "department", "肾脏科", "科室查询"),
            ("", "main", None, "空查询"),
        ]
        
        all_passed = True
        for query, scope, dept, desc in test_cases:
            try:
                context = build_query_context(query, scope=scope, department=dept)
                if context is None:
                    print_warning(f"  ✗ {desc}: 返回 None")
                    all_passed = False
                else:
                    print_success(f"  ✓ {desc}")
                    print_info(f"    查询: '{context.normalized_query}' | 范围: {context.normalized_scope} | 科室: {context.department}")
            except Exception as e:
                print_error(f"  ✗ {desc}: {e}")
                all_passed = False
        
        if all_passed:
            record_test_result(test_name, test_num, True)
            return True
        else:
            record_test_result(test_name, test_num, False, "部分测试失败")
            return False
            
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 rag_query 模块导入和函数签名")
        record_test_result(test_name, test_num, False, error_msg, "检查模块导入")
        return False


# ==============================================
# 【测试 6】Redis 缓存
# ==============================================
def test_6_redis_cache():
    """【第四阶段】测试：Redis 缓存系统"""
    test_name = "[4️⃣ 查询] Redis 缓存 (rag_cache.RAGCache)"
    test_num = 8
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.rag_cache import RAGCache, create_redis_client
        from langchain_core.documents import Document
        
        # 创建缓存对象
        client = create_redis_client()
        if client is None:
            print_warning("Redis 连接失败（可能 Redis 未启动）")
            print_diagnostic("启动 Redis: redis-server 或在 Docker 中运行 Redis")
            print_info("缓存系统将以降级模式运行（禁用缓存）")
            record_test_result(test_name, test_num, False, "Redis 不可用", "启动 Redis 服务")
            return False
        
        cache = RAGCache(client=client, ttl_seconds=300)
        
        # 测试缓存写入
        test_key = "test_key_123"
        test_answer = "测试答案"
        test_docs = [Document(page_content="测试内容", metadata={"source": "test.txt"})]
        
        cache.set(test_key, test_answer, test_docs)
        print_success(f"缓存写入成功 (键: {test_key})")
        
        # 测试缓存读取
        cached_result = cache.get(test_key)
        if cached_result is None:
            print_error("缓存读取失败")
            record_test_result(test_name, test_num, False, "缓存读取失败")
            return False
        
        cached_answer, cached_docs = cached_result
        if cached_answer != test_answer or len(cached_docs) != len(test_docs):
            print_error("缓存数据不匹配")
            record_test_result(test_name, test_num, False, "缓存数据不一致")
            return False
        
        print_success(f"缓存读取成功 (答案: {cached_answer})")
        
        # 清理测试数据
        if client:
            client.delete(test_key)
        
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 Redis 连接配置和网络")
        record_test_result(test_name, test_num, False, error_msg, "检查 Redis 配置")
        return False


# ==============================================
# 【测试 7】结果格式化
# ==============================================
def test_7_result_formatter():
    """【第六阶段】测试：检索结果格式化"""
    test_name = "[6️⃣ 输出] 结果格式化 (rag_formatter.format_documents_as_answer)"
    test_num = 12
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.rag_formatter import format_documents_as_answer
        from langchain_core.documents import Document
        
        # 创建测试文档
        test_docs = [
            Document(page_content="肌酐升高提示肾功能下降", metadata={"source": "医学文献.txt"}),
            Document(page_content="正常肌酐范围 60-115 μmol/L", metadata={"source": "参考值.txt"}),
        ]
        
        # 格式化
        formatted = format_documents_as_answer(test_docs)
        if not formatted:
            print_error("格式化返回空结果")
            record_test_result(test_name, test_num, False, "格式化为空")
            return False
        
        # 检查格式
        if "【来源】" not in formatted or "医学文献" not in formatted:
            print_error("格式化结果不符合预期")
            record_test_result(test_name, test_num, False, "格式不正确")
            return False
        
        print_success("结果格式化成功")
        print_info(f"格式化结果预览:\n{formatted[:200]}...")
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 rag_formatter 模块函数签名")
        record_test_result(test_name, test_num, False, error_msg, "检查格式化函数")
        return False


# ==============================================
# 【测试 8】参考值查询
# ==============================================
def test_8_reference_ranges():
    """【第五阶段】测试：检验指标参考值查询（可选补充）"""
    test_name = "[5️⃣ 检索] 参考值查询 (reference_ranges.get_reference_range)"
    test_num = 11
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.reference_ranges import get_reference_range, REFERENCE_RANGES
        
        # 列出可用的指标
        available_indicators = list(REFERENCE_RANGES.keys())[:5]
        print_info(f"可用指标示例: {', '.join(available_indicators)}")
        
        # 测试查询
        if "Cr" not in REFERENCE_RANGES:
            print_warning("肌酐(Cr)指标不在参考值库中")
            print_diagnostic("检查 reference_ranges.py 中的 REFERENCE_RANGES 字典")
            record_test_result(test_name, test_num, False, "指标缺失")
            return False
        
        # 获取肌酐参考值
        ref_range = get_reference_range("Cr")
        if not ref_range:
            print_warning("返回空参考值")
            print_diagnostic("检查指标是否有对应的参考范围")
            record_test_result(test_name, test_num, False, "参考值为空")
            return False
        
        print_success(f"参考值查询成功 (Cr)")
        print_info(f"  最小值: {ref_range.get('min', 'N/A')}")
        print_info(f"  最大值: {ref_range.get('max', 'N/A')}")
        print_info(f"  单位: {REFERENCE_RANGES['Cr'].get('unit', 'N/A')}")
        
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 reference_ranges 模块和参考值数据")
        record_test_result(test_name, test_num, False, error_msg, "检查参考值数据库")
        return False


# ==============================================
# 【测试 9】文本清洁
# ==============================================
def test_9_text_cleaner():
    """【第二阶段】测试：文本清洁功能"""
    test_name = "[2️⃣ 数据] 文本清洁 (text_cleaner.clean_documents)"
    test_num = 4
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.text_cleaner import clean_text, clean_document
        from langchain_core.documents import Document
        
        # 测试清洁函数
        test_cases = [
            ("  文本  \n\n\n  内容  ", "去除首尾空格和多余空行"),
            ("文本\r\n内容", "统一换行符"),
            ("文本\ufeff内容", "去除 BOM 头"),
            ("文本\x00\x01内容", "去除控制字符"),
        ]
        
        all_passed = True
        for text, desc in test_cases:
            try:
                cleaned = clean_text(text)
                if cleaned:
                    print_success(f"  ✓ {desc}")
                else:
                    print_warning(f"  ⚠ {desc}: 清洁结果为空")
                    all_passed = False
            except Exception as e:
                print_error(f"  ✗ {desc}: {e}")
                all_passed = False
        
        # 测试文档清洁
        doc = Document(page_content="  测试  \n\n\n  文档  ", metadata={"source": "test.txt"})
        cleaned_doc = clean_document(doc)
        if not cleaned_doc or not cleaned_doc.page_content:
            print_error("文档清洁失败")
            record_test_result(test_name, test_num, False, "文档清洁失败")
            return False
        
        print_success(f"文档清洁成功: '{cleaned_doc.page_content}'")
        
        if all_passed:
            record_test_result(test_name, test_num, True)
            return True
        else:
            record_test_result(test_name, test_num, False, "部分清洁失败")
            return False
            
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 text_cleaner 模块的清洁函数")
        record_test_result(test_name, test_num, False, error_msg, "检查清洁函数")
        return False


# ==============================================
# 【测试 10】文本分块
# ==============================================
def test_10_chunk_strategies():
    """【第二阶段】测试：文本分块策略"""
    test_name = "[2️⃣ 数据] 文本分块 (chunk_strategies.split_documents)"
    test_num = 5
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.chunk_strategies import split_documents
        from langchain_core.documents import Document
        
        # 创建长文本
        long_text = "这是测试文本。" * 100  # 约 700 字符
        doc = Document(page_content=long_text, metadata={"source": "test.txt"})
        
        # 分块
        chunks = split_documents([doc], chunk_size=500, chunk_overlap=50)
        
        if not chunks:
            print_error("分块返回空结果")
            record_test_result(test_name, test_num, False, "分块为空")
            return False
        
        print_success(f"文本分块成功，分成 {len(chunks)} 块")
        
        # 检查每块大小
        for i, chunk in enumerate(chunks, 1):
            if len(chunk.page_content) > 500:
                print_warning(f"  第 {i} 块超过限制大小: {len(chunk.page_content)} > 500")
            else:
                print_info(f"  第 {i} 块: {len(chunk.page_content)} 字符")
        
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 chunk_strategies 模块和分块参数")
        record_test_result(test_name, test_num, False, error_msg, "检查分块策略")
        return False


# ==============================================
# 【测试 11】文档加载
# ==============================================
def test_11_document_loaders():
    """【第二阶段】测试：文档加载功能（数据源）"""
    test_name = "[2️⃣ 数据] 文档加载 (document_loaders.load_text_documents)"
    test_num = 3
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.document_loaders import load_text_documents
        
        # 检查文档目录
        main_docs_dir = os.path.join(PROJECT_DIR, "knowledge", "main_agent_docs")
        if not os.path.exists(main_docs_dir):
            print_warning(f"文档目录不存在: {main_docs_dir}")
            print_diagnostic("创建文档目录或将文档文件放入该目录")
            record_test_result(test_name, test_num, False, "文档目录不存在", "创建文档目录")
            return False
        
        # 加载文档
        docs = load_text_documents(main_docs_dir)
        
        if not docs:
            print_warning(f"未加载到任何文档")
            print_diagnostic(f"检查 {main_docs_dir} 目录中是否有 .txt 文件")
            record_test_result(test_name, test_num, False, "未加载到文档", "检查文档文件")
            return False
        
        print_success(f"文档加载成功，加载 {len(docs)} 个文档")
        
        for i, doc in enumerate(docs[:3], 1):
            source = doc.metadata.get("source", "unknown") if doc.metadata else "unknown"
            preview = doc.page_content[:100].replace('\n', ' ')
            print_info(f"  [{i}] {source}: {preview}...")
        
        if len(docs) > 3:
            print_info(f"  ... 还有 {len(docs) - 3} 个文档")
        
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 document_loaders 模块和文档格式")
        record_test_result(test_name, test_num, False, error_msg, "检查文档加载器")
        return False


# ==============================================
# 【测试 12】知识图谱增强
# ==============================================
def test_12_knowledge_graph():
    """【第五阶段】测试：知识图谱上下文检索（可选增强）"""
    test_name = "[5️⃣ 检索] 知识图谱增强 (rag_graph.GraphContextRetriever)"
    test_num = 10
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.rag_graph import GraphContextRetriever
        from knowledge.reference_ranges import REFERENCE_RANGES
        
        # 创建知识图谱检索器
        try:
            retriever = GraphContextRetriever()
            print_success("知识图谱检索器创建成功")
        except Exception as e:
            print_warning(f"知识图谱检索器创建失败: {e}")
            print_diagnostic("这可能是因为 GraphLoader 不可用（可选组件）")
            print_info("系统将使用备用方案（参考值库）")
            record_test_result(test_name, test_num, False, "知识图谱不可用", "这是可选组件")
            return False
        
        # 测试检索
        query = "肌酐升高"
        try:
            context = retriever.retrieve_context(query)
            if context:
                print_success(f"知识图谱检索成功")
                print_info(f"  检索结果: {str(context)[:200]}...")
            else:
                print_warning("知识图谱检索返回空结果")
        except Exception as e:
            print_warning(f"知识图谱检索异常: {e}")
            print_diagnostic("这可能是图谱数据不完整（可选组件）")
        
        record_test_result(test_name, test_num, True)
        return True
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_info("知识图谱是可选组件，系统可在不依赖该组件的情况下运行")
        print_diagnostic("如需启用，请检查 rag_graph.py 和 GraphLoader 配置")
        record_test_result(test_name, test_num, False, error_msg, "知识图谱是可选的")
        return False


# ==============================================
# 【测试 13】完整 RAG 流程
# ==============================================
def test_13_complete_rag():
    """【第七阶段】测试：完整 RAG 系统端到端流程（集成验证）"""
    test_name = "[7️⃣ 集成] 完整 RAG 流程 (rag.RAGSystem.retrieve)"
    test_num = 13
    print_test_start(test_name, test_num)
    
    try:
        from knowledge.rag import RAGSystem, retrieve_medical_knowledge
        
        # 初始化 RAG 系统
        print_info("正在初始化 RAG 系统...")
        rag_system = RAGSystem()
        print_success("RAG 系统初始化成功")
        
        # 执行检索
        query = "肌酐升高"
        print_info(f"执行查询: '{query}'...")
        
        try:
            result, sources = retrieve_medical_knowledge(query, scope="main")
            
            if not result:
                print_warning("检索返回空结果")
                print_diagnostic("这可能是因为向量库为空或不包含相关文档")
                record_test_result(test_name, test_num, False, "检索结果为空", "检查文档内容")
                return False
            
            print_success(f"RAG 检索成功")
            print_info(f"  结果长度: {len(result)} 字符")
            print_info(f"  结果预览: {result[:200]}...")
            
            if sources:
                print_info(f"  返回 {len(sources)} 个文档源")
                for source in sources[:3]:
                    print_info(f"    - {source.metadata.get('source', 'unknown') if source.metadata else 'unknown'}")
            
            record_test_result(test_name, test_num, True)
            return True
            
        except Exception as e:
            print_error(f"RAG 检索执行失败: {e}")
            print_diagnostic("检查向量库、API 配置、Redis 连接")
            record_test_result(test_name, test_num, False, str(e), "检查 RAG 系统配置")
            return False
        
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print_error(error_msg)
        print_diagnostic("检查 rag.py 模块的初始化和检索方法")
        record_test_result(test_name, test_num, False, error_msg, "检查 RAG 系统")
        return False


# ==============================================
# 【测试报告生成】
# ==============================================
def print_test_report():
    """生成测试报告"""
    print_header("📊 测试结果汇总")
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    
    # 汇总统计
    print(f"{Colors.BOLD}总测试数: {total}  通过: {Colors.GREEN}{passed}{Colors.RESET}  失败: {Colors.RED}{failed}{Colors.RESET}{Colors.RESET}\n")
    
    # 详细结果
    print(f"{Colors.BOLD}详细结果:{Colors.RESET}")
    for result in test_results:
        status = f"{Colors.GREEN}✓ 通过{Colors.RESET}" if result["passed"] else f"{Colors.RED}✗ 失败{Colors.RESET}"
        print(f"  [{result['test_num']}] {result['test_name']}: {status}")
        if result["error_msg"]:
            print(f"      错误: {result['error_msg']}")
        if result["diagnostic"]:
            print(f"      诊断: {result['diagnostic']}")
    
    # 成功率
    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"\n{Colors.BOLD}成功率: {success_rate:.1f}%{Colors.RESET}")
    
    # 输出报告文件
    report_file = os.path.join(CURRENT_DIR, f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": success_rate,
            "results": test_results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n{Colors.CYAN}报告已保存到: {report_file}{Colors.RESET}")


# ==============================================
# 【主函数】
# ==============================================
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Knowledge 模块完整链路测试套件")
    parser.add_argument("--test", type=int, default=0, help="运行指定的测试（1-13），默认全部运行")
    args = parser.parse_args()
    
    print_header("🚀 Knowledge 模块完整链路测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 定义所有测试（按 RAG 真实执行流程排序）
    all_tests = [
        # 第一阶段：基础设置
        test_1_create_embeddings,      # 1️⃣ 嵌入模型创建
        test_2_load_vectorstore,        # 1️⃣ 向量库加载
        # 第二阶段：数据处理（离线）
        test_11_document_loaders,       # 2️⃣ 文档加载
        test_9_text_cleaner,            # 2️⃣ 文本清洁
        test_10_chunk_strategies,       # 2️⃣ 文本分块
        # 第三阶段：向量库构建
        test_3_build_vectorstore,       # 3️⃣ 向量库构建
        # 第四阶段：在线查询处理
        test_5_query_context,           # 4️⃣ 查询标准化
        test_6_redis_cache,             # 4️⃣ Redis 缓存
        # 第五阶段：检索阶段
        test_4_similarity_search,       # 5️⃣ 向量相似度检索
        test_12_knowledge_graph,        # 5️⃣ 知识图谱增强
        test_8_reference_ranges,        # 5️⃣ 参考值查询
        # 第六阶段：结果处理
        test_7_result_formatter,        # 6️⃣ 结果格式化
        # 第七阶段：完整集成
        test_13_complete_rag,           # 7️⃣ 完整 RAG 流程
    ]
    
    # 运行指定测试或全部
    if args.test > 0:
        if args.test <= len(all_tests):
            all_tests[args.test - 1]()
        else:
            print_error(f"测试 {args.test} 不存在（1-{len(all_tests)}）")
            sys.exit(1)
    else:
        for test_func in all_tests:
            test_func()
            print()  # 测试间隔
    
    # 打印报告
    print_test_report()
    
    # 返回状态码
    failed_count = sum(1 for r in test_results if not r["passed"])
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
