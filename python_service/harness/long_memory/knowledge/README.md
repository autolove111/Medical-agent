# knowledge 目录说明

## 1. 目录定位

`langchain_service/knowledge` 是项目里和医疗知识库、向量库、RAG 检索相关的核心目录。

它主要负责三类事情：

1. 管理知识源文件  
   包括主知识库、科室知识库、医学参考资料。

2. 构建和加载向量库  
   把文本切分、向量化、保存成 FAISS 索引，并在运行时按需加载。

3. 提供 RAG 检索能力  
   根据用户问题构造查询上下文、检索向量库、结合图谱信息、格式化结果并做缓存。

---

## 2. 目录结构概览

### 数据目录

- `main_agent_docs/`
  - 主知识库语料目录，存放通用医学知识文档。

- `dept_agent_docs/`
  - 科室知识库目录，按文件区分不同科室，例如 `呼吸科.txt`、`肾内科.txt`。

- `vector_db/`
  - 本地 FAISS 向量库存储目录。
  - `main/` 一般保存主知识库索引。
  - `department_xxx/` 一般保存科室级索引。

- `__pycache__/`
  - Python 运行时自动生成的缓存目录。

### 核心代码文件

- `__init__.py`
- `document_loaders.py`
- `text_cleaner.py`
- `chunk_strategies.py`
- `embedding_FAISS.py`
- `build_vectorstore.py`
- `rag.py`
- `rag_query.py`
- `rag_retriever.py`
- `rag_graph.py`
- `rag_cache.py`
- `rag_formatter.py`
- `medical_knowledge.py`
- `reference_ranges.py`

---

## 3. 每个文件的作用

### `__init__.py`

这个文件是 `knowledge` 包的统一导出入口。

当前主要导出了：

- `RAGSystem`
- `retrieve_medical_knowledge`

也就是说，外部模块如果要调用知识检索能力，通常可以直接从这里导入。

---

### `document_loaders.py`

这是知识文档加载入口。

当前职责：

- 维护知识库目录路径：
  - `MAIN_DOCS_DIR`
  - `DEPT_DOCS_DIR`
  - `MEDICAL_DOCS_DIR`

- 定义支持的文件格式：
  - `.txt`
  - `.md`
  - `.pdf`
  - `.docx`

- 根据扩展名自动分发不同 loader：
  - `TextLoader`
  - `PyPDFLoader`
  - `Docx2txtLoader`

- 提供统一加载函数：
  - `load_text_documents()`
  - `load_main_corpus()`
  - `load_all_dept_docs()`
  - `load_medical_corpus()`

- 提供目录扫描和路径解析能力：
  - `iter_supported_document_files()`
  - `iter_department_sources()`
  - `resolve_main_corpus_dir()`
  - `resolve_medical_docs_dir()`

可以把它理解为：知识文件进入系统的第一站。

---

### `text_cleaner.py`

这是文本清洗模块。

主要作用：

- 去掉 BOM
- 统一换行
- 去掉控制字符
- 去掉行尾多余空格
- 压缩过多空行
- 过滤空文档

核心函数：

- `clean_text()`
- `clean_document()`
- `clean_documents()`

它的定位是把原始知识文档处理成更适合切块和向量化的文本。

---

### `chunk_strategies.py`

这是文档切块模块。

主要作用：

- 基于 `RecursiveCharacterTextSplitter` 对长文档做切分
- 统一切块策略和分隔符

核心函数：

- `create_recursive_splitter()`
- `split_documents()`

它的作用是在“清洗后的文档”和“向量化”之间搭一层，把长文本拆成可检索的小块。

---

### `embedding_FAISS.py`

这是知识库向量化和 FAISS 管理的核心模块，也是整个目录里最重要的基础模块之一。

主要职责：

1. 创建 embedding 模型
   - `create_embeddings()`
   - 支持本地 embedding
   - 支持 DashScope embedding

2. 生成向量库存储路径
   - `sanitize_scope_key()`
   - `resolve_vectorstore_dir()`
   - `get_vectorstore_candidate_paths()`

3. 加载已有 FAISS 索引
   - `load_vectorstore_from_dir()`

4. 加载并清洗源文档
   - `load_documents_for_source()`
   - `load_default_medical_documents()`

5. 从文档构建向量库
   - `build_vectorstore_from_documents()`
   - `build_vectorstore_for_source()`
   - `build_main_vectorstore()`
   - `build_department_vectorstores()`

它相当于“知识文档 -> 向量库”的主加工厂。

---

### `build_vectorstore.py`

这是离线构建向量库的脚本入口。

主要作用：

- 调用 `embedding_FAISS.py` 中的构建函数
- 构建主知识库向量索引
- 构建科室知识库向量索引

它更像一个命令行入口，而不是底层能力模块。

一般在以下场景使用：

- 新增知识文档后重新建库
- 初始化环境时生成索引
- 更换 embedding 模型后重建索引

---

### `rag.py`

这是运行时 RAG 系统的总入口。

核心类：

- `RAGSystem`

主要职责：

1. 初始化 embedding
2. 初始化缓存
3. 初始化图谱检索器
4. 初始化检索器注册中心
5. 对外暴露统一的 `retrieve()` 方法

主要流程：

- 构造查询上下文
- 获取 scoped retriever
- 先查缓存
- 检索向量库
- 检索图谱上下文
- 合并文档
- 格式化输出
- 写回缓存

对外还提供：

- `retrieve_medical_knowledge()`

这个文件可以理解为“在线检索的调度中心”。

---

### `rag_query.py`

这是查询上下文标准化模块。

主要作用：

- 规范用户查询文本
- 规范检索 scope
- 生成 `scope_key`
- 生成缓存 key
- 封装 `QueryContext`

核心内容：

- `normalize_query_text()`
- `normalize_scope()`
- `resolve_scope_key()`
- `build_cache_key()`
- `QueryContext`
- `build_query_context()`

它的意义在于把“查询参数”标准化，避免缓存错乱、范围错乱、路径错乱。

---

### `rag_retriever.py`

这是检索器注册与向量库懒加载模块。

核心类：

- `ScopedRetrieverRegistry`

主要职责：

1. 缓存向量库对象
2. 缓存 retriever 对象
3. 根据 `scope` / `department` 按需加载向量库
4. 主库缺失时自动触发构建
5. 为外部返回统一的 retriever

它解决的是“运行时要查哪个库、怎么加载、怎么复用”的问题。

如果说 `embedding_FAISS.py` 负责“建库”，那这个文件负责“用库”。

---

### `rag_graph.py`

这是图谱上下文补充模块。

核心类：

- `GraphContextRetriever`

主要职责：

- 从用户问题里抽取医学指标名
- 用指标关系图谱补充上下文
- 返回图谱关联的 `Document`

典型补充信息包括：

- 指标之间的关系
- 指标关联的科室
- 图谱边的描述信息

它的作用不是替代向量检索，而是给 RAG 增加一层结构化医学关联信息。

---

### `rag_cache.py`

这是 RAG 缓存模块。

核心类：

- `RAGCache`

主要职责：

- 创建 Redis 客户端
- 根据 cache key 读取缓存
- 保存答案和对应文档列表

缓存内容包括：

- 检索结果文本
- 来源文档序列化结果

它主要用于减少重复查询带来的重复检索与重复格式化开销。

---

### `rag_formatter.py`

这是 RAG 文档序列化和输出格式化模块。

主要作用：

- `serialize_documents()`
  - 把 `Document` 转成可缓存的字典结构

- `deserialize_documents()`
  - 把缓存数据还原成 `Document`

- `format_documents_as_answer()`
  - 把检索到的多个文档拼接成最终文本答案

它负责的是“检索结果如何落盘、如何恢复、如何展示”。

---

### `medical_knowledge.py`

这是一个兼容层知识库模块。

它的定位不是主 RAG 流程入口，而是提供一个“轻量知识库对象”给其他模块复用。

核心类：

- `KnowledgeBase`
- `PatientHistoryEnhancer`

主要职责：

1. 扫描本地知识目录
2. 复用 `document_loaders.py` 读取多格式文档
3. 构建一个轻量级 FAISS 库
4. 提供简单检索能力
5. 提供病史增强能力
6. 基于 `reference_ranges.py` 做化验指标异常分析

主要函数：

- `create_knowledge_base()`

它更偏“兼容型工具模块”，而 `rag.py` 是正式的在线检索入口。

---

### `reference_ranges.py`

这是检验指标参考范围数据库。

它是一个比较大的静态数据文件，主要保存各种医学指标的：

- 中文名
- 单位
- 儿童/成人/老人参考范围
- 男女参考范围
- 危急值
- 描述信息

主要用于：

- 指标异常判断
- 病史增强
- 结构化医学解释
- 图谱和问答里的辅助解释

它提供的是“医学参考值知识”，不是 RAG 检索文本本身。

---

## 4. 整个 knowledge 目录的主流程

这个目录整体上可以分成两个阶段：

1. 离线建库阶段
2. 在线检索阶段

---

## 5. 离线建库流程

### 第一步：准备知识源文件

知识文件放在：

- `main_agent_docs/`
- `dept_agent_docs/`
- `medical_docs/`（如果存在）

文档格式现在支持：

- `.txt`
- `.md`
- `.pdf`
- `.docx`

---

### 第二步：加载文档

入口模块是：

- `document_loaders.py`

它负责：

- 扫描目录
- 识别文件格式
- 分配对应 loader
- 产出 `Document` 列表

---

### 第三步：清洗文档

入口模块是：

- `text_cleaner.py`

作用：

- 清除乱码和脏字符
- 统一文本格式
- 过滤空文档

---

### 第四步：切分文档

入口模块是：

- `chunk_strategies.py`

作用：

- 将长文档拆成适合向量检索的文本块

---

### 第五步：向量化并构建 FAISS

入口模块是：

- `embedding_FAISS.py`

作用：

- 创建 embedding 模型
- 把文本块转成向量
- 构建 FAISS 索引
- 保存到 `vector_db/`

---

### 第六步：通过脚本执行建库

脚本入口：

- `build_vectorstore.py`

它会调用：

- `build_main_vectorstore()`
- `build_department_vectorstores()`

最终产物是：

- `vector_db/main/`
- `vector_db/department_xxx/`

---

## 6. 在线检索流程

### 第一步：接收用户问题

在线入口通常是：

- `rag.py`

对外接口：

- `RAGSystem.retrieve()`
- `retrieve_medical_knowledge()`

---

### 第二步：构造查询上下文

入口模块：

- `rag_query.py`

主要工作：

- 标准化 query
- 标准化 scope
- 生成 scope_key
- 生成 cache_key

这一步解决“查主库还是科室库、缓存如何命中”的问题。

---

### 第三步：获取检索器

入口模块：

- `rag_retriever.py`

主要工作：

- 检查内存里是否已有 retriever
- 没有则加载本地 FAISS
- 主库缺失时自动建库
- 返回对应 scope 的 retriever

---

### 第四步：先查缓存

入口模块：

- `rag_cache.py`

如果 Redis 可用：

- 命中缓存则直接返回结果
- 未命中再继续检索

---

### 第五步：向量检索

retriever 从 FAISS 中召回相关文档块。

这些文档块的来源通常是：

- 主知识库
- 科室知识库

---

### 第六步：图谱补充

入口模块：

- `rag_graph.py`

它会：

- 从 query 中抽取检验指标
- 查询指标图谱
- 生成额外的图谱说明文档

这部分结果会和向量检索结果拼接。

---

### 第七步：格式化结果

入口模块：

- `rag_formatter.py`

把：

- 向量检索文档
- 图谱补充文档

整理成最终文本答案。

---

### 第八步：写回缓存

入口模块：

- `rag_cache.py`

保存：

- 格式化答案
- 原始来源文档

方便下次相同查询直接命中。

---

## 7. 一个简化版流程图

```text
知识文件(.txt/.md/.pdf/.docx)
        |
        v
document_loaders.py
        |
        v
text_cleaner.py
        |
        v
chunk_strategies.py
        |
        v
embedding_FAISS.py
        |
        v
vector_db/ (FAISS索引)


用户问题
   |
   v
rag.py
   |
   v
rag_query.py  ->  生成 QueryContext / cache_key / scope_key
   |
   v
rag_retriever.py  ->  加载对应 vectorstore / retriever
   |
   +--> rag_cache.py 先查缓存
   |
   +--> FAISS 检索知识块
   |
   +--> rag_graph.py 补充图谱上下文
   |
   v
rag_formatter.py
   |
   v
最终知识检索结果
```

---

## 8. 当前建议的理解方式

如果你后面要继续维护这个目录，最推荐按下面的心智模型理解：

- `document_loaders.py`
  - 负责“把文件读进来”

- `text_cleaner.py`
  - 负责“把文本洗干净”

- `chunk_strategies.py`
  - 负责“把长文本切小块”

- `embedding_FAISS.py`
  - 负责“把知识做成向量库”

- `build_vectorstore.py`
  - 负责“执行建库脚本”

- `rag_query.py`
  - 负责“规范查询参数”

- `rag_retriever.py`
  - 负责“按范围找对库”

- `rag_graph.py`
  - 负责“补充结构化图谱上下文”

- `rag_cache.py`
  - 负责“缓存检索结果”

- `rag_formatter.py`
  - 负责“把结果拼成可返回文本”

- `rag.py`
  - 负责“把上面所有模块串起来”

- `medical_knowledge.py`
  - 负责“轻量兼容知识库能力”

- `reference_ranges.py`
  - 负责“医学指标参考值知识”

---

## 9. 后续如果你继续扩展这个目录，通常改哪里

### 如果要新增支持的文件格式

优先改：

- `document_loaders.py`
- `requirements.txt`

### 如果要调整切块策略

优先改：

- `chunk_strategies.py`

### 如果要换 embedding 模型

优先改：

- `embedding_FAISS.py`
- `core.config`

### 如果要优化检索范围逻辑

优先改：

- `rag_query.py`
- `rag_retriever.py`

### 如果要增强答案组织方式

优先改：

- `rag_formatter.py`
- `rag.py`

### 如果要增加医学规则或异常值判断

优先改：

- `reference_ranges.py`
- `medical_knowledge.py`

---

## 10. 总结

`knowledge` 目录本质上是一套“医疗知识入库 + 向量化 + 检索增强”的完整闭环：

1. 文档进入系统  
2. 清洗与切块  
3. 构建向量库  
4. 运行时按范围检索  
5. 图谱补充上下文  
6. 缓存与格式化返回结果

如果你把它看成一条流水线，会更容易理解：

`知识文件 -> 文本处理 -> 向量库 -> 检索器 -> RAG结果`

