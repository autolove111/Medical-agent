# Medical-agent 项目改动总结

> 更新时间：2026-06-18
> 分支：`zml_1`（基于 `zly_3`）
> 涵盖：嵌入模型替换 → OCR 引擎迁移 → Reranker 精排引入

---

## ⚠️ 模型文件说明

以下两个模型**未包含在 Git 仓库中**（已在 `.gitignore` 排除 `models/`，文件过大无法版本控制），需自行下载到指定目录：

### 1. 嵌入模型：Zhinao-ChineseModernBert-Embedding

| 项目 | 详情 |
|------|------|
| 用途 | 将医学文档文本编码为 768 维向量，供 FAISS 语义检索 |
| HuggingFace | https://huggingface.co/qihoo360/Zhinao-ChineseModernBert-Embedding |
| ModelScope（国内推荐） | https://modelscope.cn/models/ZhipuAI/Zhinao-ChineseModernBert-Embedding |
| 下载到 | `models/Zhinao-ChineseModernBert-Embedding/` |
| ModelScope CLI | `modelscope download ZhipuAI/Zhinao-ChineseModernBert-Embedding --local_dir models/Zhinao-ChineseModernBert-Embedding` |

### 2. 重排模型：bge-reranker-base

| 项目 | 详情 |
|------|------|
| 用途 | Cross-Encoder 语义精排，对 FAISS 召回的 Top-20 文档逐对打分排序 |
| HuggingFace | https://huggingface.co/BAAI/bge-reranker-base |
| ModelScope（国内推荐） | https://modelscope.cn/models/Xorbits/bge-reranker-base |
| 下载到 | `models/bge-reranker-base/` |
| ModelScope CLI | `modelscope download Xorbits/bge-reranker-base --local_dir models/bge-reranker-base` |

> **自动下载**：如果本地 `models/` 目录缺失，代码会自动尝试 ModelScope → HuggingFace 下载。但建议手动预下载以加速首次启动。

---

## 一、嵌入模型替换

**目标**：将嵌入模型从 BCE-embedding 替换为 Zhinao-ChineseModernBert-Embedding。

### 改动的文件

| 文件 | 改动 |
|------|------|
| `python_service/.env` | `RAG_LOCAL_EMBEDDING_PATH` 从 `bce-embedding-base_v1` 改为 `Zhinao-ChineseModernBert-Embedding` |
| `python_service/core/config.py` | 默认模型路径、`RAG_EMBEDDING_DEVICE` 配置项 |
| `python_service/service/rag/embedding.py` | 默认模型 ID 改为 `qihoo360/Zhinao-ChineseModernBert-Embedding`，新增 ModelScope 自动下载 |

### 关键设计

- **加载优先级**：本地 `models/` 目录 → ModelScope `snapshot_download` → HuggingFace
- **兼容性**：`SentenceTransformer` 完全兼容 ModernBERT，无需改 `BCEFlagEmbedding` 类
- **向量维度**：768 维，`max_length=512`

---

## 二、OCR 引擎迁移

**目标**：将 OCR 从 PaddleOCR/DashScope 替换为 MinerU 精准解析 API。

### 改动的文件

| 文件 | 改动 |
|------|------|
| `python_service/core/config.py` | 新增 `OCR_ENGINE`、`MINERU_API_BASE_URL`、`MINERU_API_TOKEN`、`MINERU_POLL_INTERVAL`、`MINERU_POLL_TIMEOUT` |
| `python_service/.env` | 写入 MinerU API token 和配置 |
| `python_service/app/business/report_pipeline.py` | 重写 `call_ocr()`，新增 MinerU 异步 4 步流程 |
| `python_service/server.py` | 启动时命令行选择 OCR 引擎 `[1] Docker [2] API` |

### MinerU API 调用流程

```
POST /api/v4/file-urls/batch        → 上传 base64 文件 → batch_id + file_urls
POST /api/v4/extract/task           → 提交 file_url    → task_id
GET  /api/v4/extract/task/{task_id} → 轮询              → state="done" + full_zip_url
下载 ZIP → 解压 → full.md           → 解析 Markdown     → gat_structured
```

### 关键设计

- **两种模式**：`OCR_ENGINE=mineru_api`（云 API）/ `mineru_docker`（本地 GPU）
- **解析策略**：优先检测 Markdown 表格，回退正则逐行解析，复用 `indicator_classifier`
- **降级保证**：MinerU 失败 → 自动回退 Mock 数据，不中断服务
- **保留兼容**：`ai-services-python/ocr_service/` 目录保留，`report.py` 路由层不改

---

## 三、Reranker 精排引入

**目标**：将 Layer 3 的粗粒度关键词打分替换为 Cross-Encoder 语义精排。

### 改动的文件

| 文件 | 动作 | 改动 |
|------|------|------|
| `python_service/core/config.py` | 改 | 新增 6 项：`RERANKER_ENABLED`、`RERANKER_MODEL_PATH`、`RERANKER_DEVICE`、`RERANKER_TOP_K(20)`、`RERANKER_FINAL_K(5)`、`RERANKER_SCORE_THRESHOLD(0.1)` |
| `python_service/.env` | 改 | 写入 `RERANKER_MODEL_PATH=../models/bge-reranker-base` |
| `python_service/service/rag/reranker.py` | **新建** | `CrossEncoderReranker` 类：lazy load + ModelScope 优先 + HuggingFace fallback |
| `python_service/service/rag/hybrid_retriever.py` | 改 | FAISS 召回 5→20、`rerank_and_truncate()` 替换为 CrossEncoder 语义打分 |

### 检索链路变化

```
用户 Query
    ↓
[Layer 1] query_rewriter 改写
    ↓
[Layer 2] reference_ranges 关键词精确匹配
    ↓
[Layer 3] FAISS 语义召回 Top-20（原 Top-5）     ← 提升召回率
    ↓
[Layer 4] CrossEncoder (query, doc) 逐对打分     ← 语义精排（替代关键词命中计数）
    ↓
[Layer 5] score ≥ 0.1 阈值过滤 → Top-5           ← 阈值过滤
```

### 关键设计

- **lazy load**：首次调用时才加载 CrossEncoder，不影响启动速度
- **降级可用**：CrossEncoder 加载失败时自动回退原关键词打分
- **ModelScope 兼容**：优先从 ModelScope 下载 `Xorbits/bge-reranker-base`
- **阈值可调**：默认 0.1，可在 `.env` 中调整 `RERANKER_SCORE_THRESHOLD`

---

## 四、性能指标（CPU 环境实测）

| 环节 | 耗时 | 说明 |
|------|------|------|
| Zhinao 嵌入（30 篇编码） | 4.6s | 构建向量库时一次性完成 |
| FAISS 语义召回 Top-20 | ~70ms | 极快，内存检索 |
| CrossEncoder 精排 20 对 | ~1.3s | 模型预热后 |
| **单次查询总计** | **~1.5s** | 模型预热后 |

### 精排效果示例

```
Query: "肌酐120偏高怎么办严重吗"

FAISS 粗排 Top-3:                 Reranker 精排 Top-3:
  1. AKI诊断标准    (0.44)   →    1. AKI诊断标准       (0.24)  ← 临床最相关
  2. 血清肌酐指标   (0.38)   →    2. 血液透析适应症    (0.10)  ↑ 提升
  3. 肾功能不全饮食 (0.37)   →    3. CKD分期标准       (0.10)  ↑ 提升
                                 4~20. 无关文档全部 < 0.06，被阈值过滤
```

---

## 五、测试验证

| 模块 | 测试脚本 | 结果 |
|------|----------|------|
| 嵌入模型 | `test_rag/test_rag_e2e.py` | ✅ 768 维编码正常 |
| 重排器 | `test_rag/test_rag_e2e.py` | ✅ 语义排序精确，阈值过滤有效 |
| 端到端 | `test_rag/test_rag_e2e.py` | ✅ 5 条医学查询全部通过 |
| OCR | 已清理 | ⚠️ API 流程打通，token 权限需确认 |
