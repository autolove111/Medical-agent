# langchain_service 文件整理完成

## 📁 文件夹结构

```
langchain_service/
│
├── core/                              ✓ 核心服务层
│   ├── main.py                        # FastAPI 主应用
│   ├── config.py                      # 配置管理
│   ├── agent_streaming.py             # 流式 Agent
│   └── __init__.py                    # 模块导入转发
│
├── knowledge/                         ✓ 知识库系统
│   ├── medical_knowledge.py           # 医学知识库
│   ├── reference_ranges.py            # 参考值范围
│   ├── rag.py                         # RAG 系统
│   ├── shared_knowledge_retriever.py  # 共享检索
│   ├── department_knowledge_base.py   # 科室知识库
│   ├── department_tools.py            # 科室工具
│   ├── department_collaboration_graph.py  # 科室协作图
│   └── __init__.py                    # 模块导入转发
│
├── graph/                             ✓ 图结构
│   ├── graph_state.py                 # 图状态
│   ├── graph_utils.py                 # 图工具
│   ├── graph_inference.py             # 图推理
│   └── __init__.py                    # 模块导入转发
│
├── task/                              ✓ 任务路由和协调
│   ├── task_router.py                 # 任务路由
│   ├── dept_coordinator.py            # 科室协调
│   ├── dept_agent_response.py         # 科室响应
│   ├── hierarchical_main_agent.py     # 层级主 Agent
│   ├── lightweight_dept_agent.py      # 轻量级科室 Agent
│   └── __init__.py                    # 模块导入转发
│
├── vision/                            ✓ 视觉分析
│   ├── vision_analyzer.py             # 视觉分析
│   └── __init__.py                    # 模块导入转发
│
├── experimental/                      ⚠️  实验性/研究文件
│   ├── gat_react_agent.py
│   ├── gat_react_diagnosis_engine.py
│   ├── expert_gat.py
│   ├── indicator_gat.py
│   ├── react_constraint_engine.py
│   ├── final_validation.py
│   └── __init__.py                    # 模块导入转发
│
├── utils/                             ✓ 工具文件
│   ├── weight_updater.py              # 权重更新
│   ├── diagnose.py                    # 诊断工具
│   └── __init__.py                    # 模块导入转发
│
├── department_knowledge/              # 科室知识库数据
├── medical_docs/                      # 医学文档
├── vector_db/                         # 向量数据库
│
├── main.py                            ✓ 启动入口转发（uvicorn 用）
├── tools.py                           ✓ 核心工具集（全局导入）
├── __init__.py                        ✓ 根目录导入转发（向后兼容）
├── requirements.txt                   ✓ Python 依赖
├── Dockerfile                         ✓ Docker 配置
└── run.bat                            ✓ 启动脚本
```

## 🚀 启动方式（保持不变）

```bash
# 方式 1: 直接使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 方式 2: 使用 run.bat
./run.bat

# 方式 3: 使用 Python
python main.py
```

## 🔄 导入兼容性

- ✅ 所有旧导入仍然可用（如 `from config import settings`）
- ✅ 新导入也支持（如 `from core.config import settings`）
- ✅ 根目录 `__init__.py` 提供统一导入转发
- ✅ 各子目录 `__init__.py` 管理本地导入

## 📊 文件统计

| 分类         | 文件数 | 说明        |
| ------------ | ------ | ----------- |
| core         | 3      | 核心服务    |
| knowledge    | 7      | 知识库系统  |
| graph        | 3      | 图结构      |
| task         | 5      | 任务协调    |
| vision       | 1      | 视觉分析    |
| experimental | 6      | 实验/研究   |
| utils        | 2      | 工具文件    |
| **总计**     | **27** | Python 文件 |

## ✨ 优势

1. **清晰的模块化** - 相关功能聚合在一起
2. **易于维护** - 找方法不用遍历整个目录
3. **易于扩展** - 新功能可以创建新模块目录
4. **向后兼容** - 所有旧的导入仍然有效
5. **清晰的依赖关系** - 哪些模块是可选的（experimental）一目了然

## 🛠️ 注意事项

- 所有导入都通过 sys.path 在 core/main.py 中配置
- 如需移动更多文件到子目录，记得更新 sys.path 配置
- experimental 目录中的文件是可选的，可以安全删除
