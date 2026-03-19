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
            self.embeddings = DashScopeEmbeddings(
                model="text-embedding-v3",
                dashscope_api_key=settings.DASHSCOPE_API_KEY
            )
            self.vectorstore = self._get_or_create_vectorstore()
            self.rag_chain = self._create_rag_chain()
            logger.info("RAG 系统初始化成功")
        except Exception as e:
            logger.error(f"RAG 系统初始化失败: {e}")

    def _load_medical_documents(self) -> List:
        documents = []
        # --- 核心修复：使用绝对路径，避免在 Windows 不同终端启动时的路径偏移 ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        doc_path = os.path.join(current_dir, "medical_docs")
        
        try:
            if os.path.exists(doc_path):
                # 修复 DirectoryLoader 配置
                loader = DirectoryLoader(
                    doc_path,
                    glob="**/*.txt",
                    loader_cls=TextLoader,
                    loader_kwargs={'encoding': 'utf-8'} # 显式指定 utf-8
                )
                documents = loader.load()
                logger.info(f"成功加载 {len(documents)} 个医学文档")
            else:
                logger.warning(f"目录 {doc_path} 不存在，准备创建默认文档")
                os.makedirs(doc_path, exist_ok=True)
                self._create_sample_medical_docs(doc_path)
                # 递归调用一次以加载刚创建的文档
                return self._load_medical_documents()
        except Exception as e:
            logger.error(f"加载文档失败详情: {e}")
        
        return documents

    def _get_or_create_vectorstore(self):
        try:
            # 优先加载现有索引
            if os.path.exists(settings.VECTOR_DB_PATH):
                return FAISS.load_local(
                    settings.VECTOR_DB_PATH,
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
            
            # 否则创建新索引
            documents = self._load_medical_documents()
            if not documents:
                return None
            
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP
            )
            chunks = text_splitter.split_documents(documents)
            vectorstore = FAISS.from_documents(chunks, self.embeddings)
            
            os.makedirs(settings.VECTOR_DB_PATH, exist_ok=True)
            vectorstore.save_local(settings.VECTOR_DB_PATH)
            return vectorstore
        except Exception as e:
            logger.error(f"向量库操作失败: {e}")
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
            return "【RAG 系统未就绪】", []
        try:
            result = self.rag_chain({"query": query})
            return result.get("result", ""), result.get("source_documents", [])
        except Exception as e:
            return f"【检索异常】{str(e)}", []

# 实例化
rag_system = RAGSystem()

def retrieve_medical_knowledge(query: str) -> Tuple[str, list]:
    return rag_system.retrieve(query)