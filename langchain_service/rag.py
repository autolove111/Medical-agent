import logging
import os
from typing import List, Tuple
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOpenAI
from config import settings

logger = logging.getLogger(__name__)

class RAGSystem:
    def __init__(self):
        self.embeddings = None
        self.vectorstore = None
        self.rag_chain = None
        self._initialize()
    
    def _initialize(self):
        try:
            logger.info("=" * 60)
            logger.info("开始初始化 RAG 系统")
            logger.info("=" * 60)
            
            logger.info("第一步：初始化 DashScope Embeddings...")
            try:
                # 检查 API Key
                api_key = settings.DASHSCOPE_API_KEY
                if not api_key or api_key == "your-dashscope-api-key":
                    logger.error("❌ DashScope API Key 未配置或为默认值")
                    logger.error("请在 .env 文件中配置 DASHSCOPE_API_KEY")
                    self.embeddings = None
                    self.vectorstore = None
                    self.rag_chain = None
                    return
                
                self.embeddings = DashScopeEmbeddings(
                    model="text-embedding-v3",
                    dashscope_api_key=api_key
                )
                logger.info("✓ Embeddings 初始化成功")
            except Exception as e:
                logger.error(f"❌ Embeddings 初始化失败: {e}", exc_info=True)
                self.embeddings = None
                self.vectorstore = None
                self.rag_chain = None
                return
            
            logger.info("第二步：初始化向量库...")
            try:
                self.vectorstore = self._get_or_create_vectorstore()
                if not self.vectorstore:
                    logger.error("❌ 向量库初始化为空")
                    self.rag_chain = None
                    return
                logger.info("✓ 向量库初始化成功")
            except Exception as e:
                logger.error(f"❌ 向量库初始化失败: {e}", exc_info=True)
                self.vectorstore = None
                self.rag_chain = None
                return
            
            logger.info("第三步：创建 RAG Chain...")
            try:
                self.rag_chain = self._create_rag_chain()
                if not self.rag_chain:
                    logger.error("❌ RAG Chain 创建失败")
                    return
                logger.info("✓ RAG Chain 创建成功")
            except Exception as e:
                logger.error(f"❌ RAG Chain 创建失败: {e}", exc_info=True)
                self.rag_chain = None
                return
            
            logger.info("=" * 60)
            logger.info("✓ RAG 系统初始化完成")
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"❌ RAG 系统初始化异常: {e}", exc_info=True)
            self.embeddings = None
            self.vectorstore = None
            self.rag_chain = None

    def _load_medical_documents(self) -> List:
        documents = []
        # --- 核心修复：使用绝对路径，避免在 Windows 不同终端启动时的路径偏移 ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        doc_path = os.path.join(current_dir, "medical_docs")
        
        logger.info(f"尝试从 {doc_path} 加载医学文档")
        
        try:
            if os.path.exists(doc_path):
                # 列出目录中的所有文件进行诊断
                files = os.listdir(doc_path)
                logger.info(f"目录中发现 {len(files)} 个文件: {files}")
                
                # 修复 DirectoryLoader 配置
                loader = DirectoryLoader(
                    doc_path,
                    glob="**/*.txt",
                    loader_cls=TextLoader,
                    loader_kwargs={'encoding': 'utf-8'} # 显式指定 utf-8
                )
                documents = loader.load()
                logger.info(f"成功加载 {len(documents)} 个医学文档")
                if not documents:
                    logger.warning("DirectoryLoader 返回空列表，可能没有 *.txt 文件")
            else:
                logger.warning(f"目录 {doc_path} 不存在，准备创建默认文档")
                os.makedirs(doc_path, exist_ok=True)
                self._create_sample_medical_docs(doc_path)
                # 递归调用一次以加载刚创建的文档
                return self._load_medical_documents()
        except Exception as e:
            logger.error(f"加载文档失败详情: {e}", exc_info=True)
        
        return documents

    def _get_or_create_vectorstore(self):
        try:
            vector_db_path = settings.VECTOR_DB_PATH
            logger.info(f"向量库路径: {vector_db_path}")
            
            # 优先加载现有索引
            if os.path.exists(vector_db_path):
                logger.info(f"发现现有向量库，尝试加载...")
                try:
                    return FAISS.load_local(
                        vector_db_path,
                        self.embeddings,
                        allow_dangerous_deserialization=True
                    )
                except Exception as e:
                    logger.warning(f"加载现有向量库失败: {e}，尝试重新创建")
            
            # 否则创建新索引
            logger.info("开始创建新的向量库...")
            documents = self._load_medical_documents()
            if not documents:
                logger.error("医学文档为空，无法创建向量库")
                return None
            
            logger.info(f"文档数量: {len(documents)}")
            
            logger.info("开始分割文档...")
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )
            chunks = text_splitter.split_documents(documents)
            logger.info(f"分割后的块数: {len(chunks)}")
            
            # 创建向量库前检查 embedding 是否可用
            if not self.embeddings:
                logger.error("Embeddings 未初始化")
                return None
            
            logger.info("使用 FAISS 创建向量库（分批处理以避免 API 限制）...")
            
            # 【关键修复】DashScope API 限制：一次最多 10 个文本
            # 需要分批调用 embedding
            vectorstore = None
            batch_size = 8  # 保险起见用 8（小于 10）
            
            for i in range(0, len(chunks), batch_size):
                batch_chunks = chunks[i:i+batch_size]
                logger.info(f"处理第 {i//batch_size + 1} 批，包含 {len(batch_chunks)} 个 chunks...")
                
                try:
                    if vectorstore is None:
                        # 第一批：创建新的 vectorstore
                        vectorstore = FAISS.from_documents(batch_chunks, self.embeddings)
                    else:
                        # 后续批次：添加到现有 vectorstore
                        new_vs = FAISS.from_documents(batch_chunks, self.embeddings)
                        vectorstore.add_documents(batch_chunks)
                except Exception as e:
                    logger.error(f"处理第 {i//batch_size + 1} 批失败: {e}", exc_info=True)
                    raise
            
            logger.info("向量库创建成功")
            
            # 保存向量库
            logger.info(f"保存向量库到 {vector_db_path}...")
            os.makedirs(vector_db_path, exist_ok=True)
            vectorstore.save_local(vector_db_path)
            logger.info("向量库保存成功")
            
            return vectorstore
        except Exception as e:
            logger.error(f"向量库操作失败: {e}", exc_info=True)
            return None

    def _create_rag_chain(self):
        if not self.vectorstore:
            return None
        
        llm = ChatOpenAI(
            model=settings.DASHSCOPE_MODEL,
            openai_api_key=settings.DASHSCOPE_API_KEY,
            openai_api_base=settings.DASHSCOPE_BASE_URL,
            temperature=settings.TEMPERATURE
        )
        
        return RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.vectorstore.as_retriever(search_kwargs={"k": settings.RAG_TOP_K}),
            return_source_documents=True
        )

    def retrieve(self, query: str) -> Tuple[str, list]:
        if not self.rag_chain:
            logger.error(f"RAG Chain 不可用。vectorstore: {self.vectorstore}, rag_chain: {self.rag_chain}")
            return "【RAG 系统未就绪】系统正在初始化，请重试或稍后再试。", []
        try:
            logger.info(f"执行 RAG 检索: {query}")
            result = self.rag_chain({"query": query})
            logger.info(f"检索成功，返回 {len(result.get('source_documents', []))} 个文档")
            return result.get("result", ""), result.get("source_documents", [])
        except Exception as e:
            logger.error(f"RAG 检索失败: {e}", exc_info=True)
            return f"【检索异常】{str(e)}", []

# 实例化
rag_system = RAGSystem()

def retrieve_medical_knowledge(query: str) -> Tuple[str, list]:
    return rag_system.retrieve(query)