# 化验单处理流程完整分析 - 用户对话总结

**对话日期**：2026 年 4 月 1 日  
**主题**：讲解系统处理化验单的完整流程

---

## 系统实际处理流程（已讲解内容总结）

### 🔄 完整处理链路

#### **阶段 1：前端上传**

```javascript
用户操作：点击"📤 上传"按钮
  ↓
选择图片文件（.jpg/.png/.pdf）
  ↓
handleFileUpload() 触发
  ↓
调用 ApiService.uploadReport(file)
  ↓
POST /api/v1/agent/upload-report (multipart/form-data)
```

#### **阶段 2：Java 后端处理上传**

```java
MedicalFacadeService.handleUploadAndAppend()
  │
  ├─ StorageService.store(file)
  │  └─ 保存文件到 {UPLOAD_DIR}/uploads/
  │  └─ 返回规范化路径：uploads/medical_20240401_xxx.jpg
  │
  ├─ 构建访问 URL
  │  ├─ browserFileUrl: http://localhost:8080/api/v1/file/view/xxx.jpg
  │  └─ ocrAccessibleUrl: http://host.docker.internal:8080/api/v1/file/view/xxx.jpg
  │
  ├─ 返回成功响应（立即返回给前端）
  │  ├─ status: "success"
  │  ├─ filePath: ocrAccessibleUrl
  │  ├─ fileUrl: browserFileUrl
  │  └─ fileName: xxx.jpg
  │
  └─ 【异步】VisionService.prefetchOcr(ocrAccessibleUrl)
     └─ CompletableFuture 后台运行（不阻塞主请求）
        └─ OcrServiceClient.prefetchVisionCache()
           └─ 预热 OCR 缓存（为后续分析做准备）
```

**关键点**：上传返回给前端的速度很快（< 1 秒），后台异步进行 OCR 预热。

#### **阶段 3：异步 OCR 预热（后台进行）**

```python
Python OCR Service (端口 8001)
  │
  ├─ 接收请求：POST /api/v1/analyze-vision
  │  └─ 请求体：{filePath: "http://...", modelName: "qwen3-vl-32b-thinking"}
  │
  ├─ 调用视觉模型进行图像识别
  │  ├─ 默认模型：qwen3-vl-32b-thinking
  │  ├─ 备选模型：gpt-4o (OpenAI)
  │  └─ 备选模型：claude-3-sonnet (Anthropic)
  │
  ├─ 模型输出格式化
  │  └─ 提取检验指标：[
  │      {
  │         "indicator": "Cr",      // 血肌酐
  │         "value": 150,
  │         "unit": "μmol/L",
  │         "reference_range": "80-115",
  │         "status": "高"
  │      },
  │      ...
  │    ]
  │
  ├─ 返回响应
  │  ├─ cached: true/false (是否来自缓存)
  │  ├─ analysis: [...] (识别结果数组)
  │  └─ model_used: "qwen3-vl-32b-thinking"
  │
  └─ 将结果存入 Redis 缓存（可选）
     └─ Key: ocr:{file_hash}:{model}
     └─ TTL: 3600 秒
```

**结果**：OCR 服务缓存了这张图片的识别结果。

#### **阶段 4：前端自动发送分析请求**

```javascript
// 上传成功回调
if (response.status === "success") {
  // 自动生成分析消息
  userInput.value = `请分析这张化验单：${response.filePath}`;

  // 立即发送，不需要用户再次点击
  await sendMessage();
}
```

**用户体验**：上传后自动进行分析，不需要手动输入命令。

#### **阶段 5：Agent 后端分析处理**

```python
# agent_streaming.py: MedicalAgent.process_query()

消息链构建：
  │
  ├─ 【步骤 1】RAG 知识库检索
  │  └─ retrieve_medical_knowledge(query)
  │     ├─ 向量库检索与"血肌酐升高"相关的医学文献
  │     ├─ 返回 Top-3 相关文档（可配置）
  │     └─ 缓存到 Redis（TTL: 86400 秒）
  │
  ├─ 【步骤 2】加载患者病历
  │  └─ query_user_medical_history(userId)
  │     ├─ 从数据库查询既往病史
  │     ├─ 从数据库查询过敏药物
  │     └─ 组合为 "【过敏药物】...\n【病历历史】..."
  │
  ├─ 【步骤 3】【新增】医学知识库分析与病历增强
  │  └─ PatientHistoryEnhancer.enhance_medical_summary()
  │     ├─ 从 reference_ranges.py 获取标准参考范围
  │     ├─ MedicalKnowledgeBase.analyze_lab_results()
  │     │  ├─ 遍历每个检验指标
  │     │  ├─ 对比参考范围，识别异常状态
  │     │  │  ├─ critical (危急值) → ⚠️🚨
  │     │  │  ├─ high (升高) → ↑
  │     │  │  ├─ low (降低) → ↓
  │     │  │  └─ normal (正常) → ✓
  │     │  └─ 返回异常指标列表
  │     │
  │     ├─ 自动推荐科室
  │     │  ├─ 根据异常指标 → 肾内科、血液科、肝胆病科等
  │     │  └─ 按相关性排序
  │     │
  │     └─ 生成增强版病历上下文
  │        ├─ 原始病历信息
  │        ├─ 当前检验结果状态汇总
  │        ├─ 具体异常指标 + 参考范围
  │        └─ 推荐科室列表
  │
  ├─ 【步骤 4】构建 LLM 提示词
  │  └─ 系统消息（固定）
  │     "你是专业的医学检验智能助手 MedLabAgent..."
  │
  └─ 【步骤 5】构建用户消息（动态拼接）
     ├─ 当前用户 ID
     ├─ 【知识库检索结果】RAG 找到的相关医学文献
     ├─ 【用户病史与参考范围】增强后的病历信息
     ├─ 【用户问题】"请分析这张化验单：filePath"
     └─ 【指导】请结合以上信息，给出结构化医学分析...
        包含：
        1. 关键指标或问题判断
        2. 可能原因分析
        3. 需要重点关注的风险
        4. 后续检查或就医建议

LLM 流式生成响应：
  │
  ├─ 调用 ChatOpenAI (DashScope API)
  ├─ 温度参数 (temperature): 0.7 （平衡创意和准确性）
  ├─ 最大 tokens: 2000
  ├─ 流式输出分块传回前端
  │  └─ 每个分块实时显示（用户看到逐词显示效果）
  │
  └─ 最后追加 META 标记（元数据提取）
     格式：[META|医疗:是|疾病:急性肾损伤|过敏:无]
     作用：告诉前端这次回复是否为医疗诊断、包含哪些疾病名、有哪些过敏信息
```

#### **阶段 6：前端接收并显示结果**

```javascript
streamChat(
  userMessage,
  (chunk) => {
    // 每接收一个分块，就追加到最后一条助手消息
    lastMsg.content += chunk;
    scrollToBottom(); // 自动滚动到底部
  },
  (metadata) => {
    // 流式完成后，提取元数据
    lastMsg.isMedical = metadata.isMedical; // 是否医学诊断
    lastMsg.extractedDiseases = metadata.diseases; // 提取的疾病
    lastMsg.extractedDrugAllergy = metadata.drugAllergies; // 提取的过敏药
    lastMsg.content = lastMsg.content.replace(/\n?\[META\|[^\]]*\]/g, ""); // 去掉 META 标记
  },
);
```

**显示内容**：

- ✅ 诊断分析文本（格式化，去掉 META 标记）
- ✅ 如果 `isMedical === true`，显示【记录到病历】按钮
- ✅ 用户可以编辑疾病名和过敏药信息

#### **阶段 7：用户确认后记录病历（可选）**

```javascript
confirmSave() {
  POST /api/v1/user/medical-history/append
  {
    disease: medicalForm.disease,        // 用户编辑的疾病名
    status: "未康复"
  }

  // Java 后端处理
  → UserMedicalService.appendMedicalHistory()
    → UPDATE users SET lifetime_medical_history = ... WHERE user_id = ?
    → 数据库记录成功
    → 下次查询时自动包含这条新病历
}
```

---

## 核心流程对标表

| 阶段  | 操作               | 耗时    | 关键特性         |
| ----- | ------------------ | ------- | ---------------- |
| **1** | 前端上传选择       | < 1s    | 用户主动         |
| **2** | Java 保存+URL 构建 | < 500ms | 同步返回         |
| **3** | 异步 OCR 预热      | 2-5s    | 后台异步，不阻塞 |
| **4** | 自动发送分析       | 0ms     | 前端自动触发     |
| **5** | Agent 分析         | 5-15s   | 流式输出         |
| **6** | 前端显示           | 实时    | 逐词显示         |
| **7** | 病历记录（可选）   | < 500ms | 用户确认后       |

**总耗时**：从上传到看到完整分析 = **5-20 秒**

---

## 新增功能详解（本次修复）

### 1️⃣ 参考范围数据库

**文件**：`langchain_service/reference_ranges.py`

- 包含 26 个关键医学指标
- 每个指标包含：名称、单位、正常范围、危急值、临床意义
- 支持性别差异化范围（如肌酐在男性和女性有不同范围）

**示例**：

```python
"Cr": {
    "name": "血肌酐",
    "unit": "μmol/L",
    "male": {"min": 80, "max": 115},
    "female": {"min": 60, "max": 93},
    "critical_high": 500,
    "description": "肾功能主要标志..."
}
```

### 2️⃣ 医学知识库模块

**文件**：`langchain_service/medical_knowledge.py`

**核心功能**：

```python
# 功能 1：单个指标异常检测
check_abnormality(indicator="Cr", value=150, gender="M")
→ {
    "is_abnormal": True,
    "level": "high",  # critical/high/low/normal
    "message": "↑ 血肌酐过高（150 μmol/L，正常值 ≤115）"
  }

# 功能 2：批量实验室结果分析
analyze_lab_results({
    "Cr": 150,
    "BUN": 15,
    "WBC": 3.0,
    "HB": 140
}, gender="M")
→ {
    "status": "ABNORMAL",
    "abnormalities": [...],
    "recommended_departments": ["肾内科", "血液科"],
    "summary": "【升高】2项指标升高；【降低】1项降低。建议及时就医。"
  }

# 功能 3：病历增强
enhancer.enhance_medical_summary(
    base_summary="既往史：无",
    current_results={"Cr": 150, ...},
    gender="M"
)
→ "既往史：无\n【当前检验结果分析】\n状态：ABNORMAL\n..."
```

### 3️⃣ Agent 集成

**文件**：`langchain_service/agent_streaming.py`

```python
class MedicalAgent:
    def __init__(self, user_id: str):
        self.kb = create_knowledge_base()           # 加载知识库
        self.enhancer = PatientHistoryEnhancer()    # 加载增强器

    def process_query(self, query, user_context, lab_results=None):
        # 如果有检验结果，进行分析和增强
        if lab_results:
            user_context = self.enhancer.enhance_medical_summary(
                user_context,
                lab_results
            )
        # 继续原有流程...
```

---

## 验证状态

✅ **已测试**（2026.04.01）

```
Test 1: Medical Knowledge Base
  ✓ 已初始化，26 个指标已加载
  ✓ 异常检测功能正常
  ✓ 批量分析功能正常

Test 2: RAG System
  ✓ Embeddings 已初始化
  ✓ 向量库已加载
  ✓ 检索功能正常

Test 3: Agent Integration
  ✓ 知识库已集成
  ✓ 病历增强器已集成
  ✓ 查询处理正常

Test 4: Query Processing
  ✓ 响应长度 1200+ 字符
  ✓ RAG 来源 3+ 文档
  ✓ 系统集成稳定
```

---

## 可能的改进方向

### 短期（立即）

1. **指标标准化**
   - 统一指标代码（目前有 Cr、Creatinine 混用的可能）
   - 添加指标别名映射

2. **参考范围本地化**
   - 支持不同医院的参考范围配置
   - 支持国际单位制 (SI Units) 转换

3. **错误处理**
   - OCR 识别失败时的降级方案
   - LLM API 超时的重试机制

### 中期（1-2 周）

1. **多指标关联分析**
   - 识别综合征（如肾功能综合征：Cr+BUN+UA 同时升高）
   - 指标间的相互影响

2. **时间序列对比**
   - 历次检验结果趋势分析
   - 异常变化预警

3. **药物相互作用检查**
   - 患者当前用药与检验异常的关联
   - 用药调整建议

### 长期（1-3 月）

1. **机器学习优化**
   - 用户反馈学习科室推荐准确性
   - 个性化分析模型

2. **多模式集成**
   - 医学影像识别（X光、B超等）
   - 患者自述症状关联

3. **国际化**
   - 多语言支持
   - 不同国家医学标准

---

## 总结

**当前系统处理流程**：

1. 📤 上传 → 保存 + 异步 OCR 预热
2. 💬 自动发送分析请求
3. 🔍 Agent 执行：RAG 检索 + 医学知识库分析 + LLM 生成
4. 📊 流式显示 + 元数据提取
5. 💾 用户确认后记录病历

**新增能力**：

- ✅ 自动检验指标异常检测
- ✅ 参考范围对标
- ✅ 科室推荐
- ✅ 病历智能增强

**系统稳定性**：

- ✅ 所有组件已验证
- ✅ 异步处理不阻塞
- ✅ 缓存优化性能
- ⚠️ Redis 可选（系统不依赖）

---

**本文档编写日期**：2026 年 4 月 1 日  
**对应修复**：RAG 系统与病历查询完整修复
