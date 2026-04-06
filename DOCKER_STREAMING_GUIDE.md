# MedLabAgent 一键启动完全指南

## 🚀 快速启动（3 分钟）

### Windows 用户 - 推荐方案

```batch
REM 方案 1: 使用 PowerShell（推荐，但如果有编码问题可改用方案2）
powershell -ExecutionPolicy Bypass -File docker-run.ps1

REM 方案 2: 直接使用 Docker Compose 命令
cd infrastructure
docker compose --project-name medlab -f docker-compose.yml --env-file ..\.env up --build
```

### Linux / macOS 用户

```bash
# 赋予脚本执行权限
chmod +x docker-run.sh

# 启动所有服务
./docker-run.sh start
```

### 最简单的方法 - 使用 Docker Compose 直接命令

```bash
# 从项目根目录运行
docker compose -f infrastructure/docker-compose.yml --env-file .env up --build
```

---

## 📡 实时推流日志查看

启动命令会自动显示 **实时的推流日志**，展示诊疗链路的完整过程：

### 完整推流日志示例

```
╔════════════════════════════════════════════════════════════════════╗
║                   医学诊疗 GAT-ReAct 推流过程                      ║
╚════════════════════════════════════════════════════════════════════╝

[java-backend] 2024-04-01 14:30:00 ✓ 应用启动成功
[python-langchain] 2024-04-01 14:30:01 ✓ LangChain Agent 初始化完成
[python-ocr] 2024-04-01 14:30:02 ✓ OCR 视觉识别服务就绪

════════════════════ 诊断请求流程 ════════════════════

2024-04-01 14:31:15 [java-backend]
  POST /api/v1/chat/stream - 患者: User#123
  Body: {
    "query": "请分析这份化验单",
    "file_id": "xyz123",
    "ocr_result": {
      "indicators": {
        "Cr": 130,
        "BUN": 15,
        "UA": 450,
        "ALT": 82,
        "GLU": 7.2
      }
    }
  }

2024-04-01 14:31:15 [python-langchain]
  [IndicatorGAT] 启动指标生理关联图推理...
  - 计算异常分数: Cr=0.91, BUN=0.50, UA=0.85, ALT=0.82, GLU=0.20
  - 运行 2 层图邻域传播
  - 关键指标簇权重: [Cr: 0.85, UA: 0.82, ALT: 0.72, BUN: 0.50]

2024-04-01 14:31:16 [python-langchain]
  [ExpertGAT] 启动专家协作图推理...
  - 指标 → 科室映射:
    • Cr → RenalDepartment (0.90)
    • UA → RenalDepartment (0.80)
    • ALT → GastroenterologyDepartment (0.85)
    • GLU → EndocrinologyDepartment (0.60)
  - 初始科室权重: {
      "RenalDepartment": 0.90,
      "GastroenterologyDepartment": 0.85,
      "EndocrinologyDepartment": 0.60,
      "CardiologyDepartment": 0.15
    }

2024-04-01 14:31:16 [python-langchain]
  [ExpertGAT 第二层] 应用科室协作关系...
  - PRECEDES: LaboratoryDepartment → RenalDepartment (权重0.8)
  - COLLABORATE: RenalDepartment ↔ CardiologyDepartment (权重0.4)
  - 最终科室权重: {
      "RenalDepartment": 0.95,
      "GastroenterologyDepartment": 0.85,
      "CardiologyDepartment": 0.38,  # 因协作关系提升
      "EndocrinologyDepartment": 0.60,
      "LaboratoryDepartment": 1.00   # 前置依赖，最高优先级
    }

2024-04-01 14:31:16 [python-langchain]
  [ReactConstraintEngine] 生成权重掩码...
  - 归一化 & 缩放×100: {
      "LaboratoryDepartment": 100,
      "RenalDepartment": 95.0,
      "GastroenterologyDepartment": 85.0,
      "EndocrinologyDepartment": 60.0,
      "CardiologyDepartment": 38.0
    }
  - 工具优先级排序:
    ① check_infection_markers (Lab)
    ② check_renal_function (Renal)
    ③ check_liver_function (Gastro)
    ④ check_glucose_level (Endo)
    ⑤ analyze_heart_rhythm (Cardio)
  - 互斥规则: 不允许同时调用 [RenalDepartment + InfectiousDepartment]

2024-04-01 14:31:17 [python-langchain]
  [GATReActDiagnosisEngine] 启动 ReAct 循环...

  ━━━━━━━━━━━━━━━━ ReAct 迭代 #1 ━━━━━━━━━━━━━━━━

  [Thought] 生成思考
    患者检验指标显示:
    · 肌酐(Cr) 严重升高 130 (正常60-110) → 肾脏异常信号强
    · 尿酸(UA) 严重升高 450 (正常150-420) → 可能痛风或肾脏代谢障碍
    · ALT 升高 82 (正常<40) → 可能肝脏受损
    · 血糖 GLU 升高 7.2 (正常3.9-6.1) → 代谢异常

    GAT 权重分析约束:
    ✓ 优先调查: LaboratoryDepartment (权重 100)
    ✓ 主要关注: RenalDepartment (权重 95)
    ✓ 次要关注: GastroenterologyDepartment (权重 85)
    ✗ 互斥规则: 不调用 InfectiousDepartment

    推理思路:
    1. 首先进行实验室检查确认各项指标
    2. 重点评估肾脏功能 (肌酐升高最显著)
    3. 检查肝脏功能 (ALT升高提示肝脏问题)
    4. 评估代谢状态 (血糖升高)

2024-04-01 14:31:18 [python-langchain]
  [Action] 提议行动
    Tool: check_renal_function (RenalDepartment)
    Priority: 1
    Allowed: true
    Input: {
      "creatinine": 130,
      "bun": 15,
      "uric_acid": 450,
      "patient_age": 45
    }

2024-04-01 14:31:18 [python-ocr]
  executing tool: check_renal_function
  method: query_knowledge_base
  query: "肌酐130 尿素氮15 尿酸450 45岁患者肾脏异常诊断"

2024-04-01 14:31:20 [python-ocr]
  ✓ Tool result received (1.2s):
  {
    "diagnosis": "可能为 CKD 2-3 期 (慢性肾脏病)",
    "gfr_estimate": 45,
    "risk_level": "中等偏高",
    "recommendations": [
      "进行24小时尿蛋白定量",
      "肾脏超声检查",
      "控制血压和血糖"
    ],
    "confidence": 0.86
  }

2024-04-01 14:31:20 [python-langchain]
  [Observation] 观察结果
    肾脏专家咨询结果:
    - 诊断假设: CKD 2-3 期
    - GFR 估算值: 45 (轻-中度肾功能损害)
    - 信心度: 0.86 (中等-高)
    - 建议进一步检查:
      1️⃣  24小时尿蛋白定量检查
      2️⃣  肾脏超声检查
      3️⃣  血压和血糖控制

2024-04-01 14:31:21 [python-langchain]
  [Thought] 第二轮思考
    基于肾脏科结果，需要进一步评估:
    · ALT升高提示可能肝脏受损
    · 血糖升高可能是继发性 (CKD 可导致代谢紊乱)
    · 需要排除药物相互作用

    下一步行动: 咨询胃肠肝胆科

2024-04-01 14:31:21 [python-langchain]
  [Action] 第二次行动
    Tool: check_liver_function (GastroenterologyDepartment)
    Priority: 3
    Input: {
      "alt": 82,
      "ast": 45,
      "tbil": 18,
      "status": "in_context_of_ckd"
    }

2024-04-01 14:31:22 [python-ocr]
  executing tool: check_liver_function
  LLM response:
  {
    "status": "肝脏轻度受损",
    "probable_cause": "可能继发于肾脏病或代谢障碍",
    "action": "建议每月复查肝功能"
  }

2024-04-01 14:31:23 [python-langchain]
  [ReAct 循环完成] 已收集充分信息，进入共识阶段

  ━━━━━━━━━━━━━━━━ 多 Agent 共识 ━━━━━━━━━━━━━━━━

2024-04-01 14:31:24 [python-langchain]
  [AgentPropose] 肾脏科专家提案
  诊断意见:
  - 主诊断: 慢性肾脏病 2-3 期
  - 可能病因: 高血压、糖尿病相关肾病
  - 信心度: 0.82

  建议:
  1. 紧急进行: 24小时尿蛋白定量 + 肾脏超声
  2. 启动: 血压控制、血糖管理
  3. 随访: 每3个月复查肾功能

2024-04-01 14:31:25 [python-langchain]
  [AgentCriticism] 消化肝胆科专家批评审查
  批评意见:
  ✓ 诊断合理，症状与 CKD 相符
  ? 需要确认: ALT升高是否独立问题还是继发表现
  ✗ 遗漏: 没有评估营养状况和贫血可能性

  补充建议:
  - 补充检查: 血清蛋白、血红蛋白
  - 营养评估

2024-04-01 14:31:26 [python-langchain]
  [ConsensusManager] 共识管理员决议
  最终诊疗方案:

  【主诊断】慢性肾脏病 (CKD) 2-3 期

  【鉴别诊断】
  - 糖尿病肾病 (DKD) - 可能性 75%
  - 高血压肾病 - 可能性 20%
  - 其他肾脏疾病 - 可能性 5%

  【立即行动】
  1. 采血检查: 肌酐定量、24小时尿蛋白、血清铁蛋白、血红蛋白
  2. 影像学: 肾脏超声检查
  3. 计算: GFR 精确值、蛋白尿定量

  【双周内完成】
  - 内分泌科评估 (血糖控制)
  - 心内科评估 (血压管理)
  - 营养科咨询

  【长期管理】
  - RAS 阻滞剂 (ACE-I 或 ARB)
  - 血压目标: <130/80 mmHg
  - 血糖目标: HbA1c <7%
  - 月度肝功能监测
  - 3个月肾功能复查

2024-04-01 14:31:27 [java-backend]
  POST /api/v1/chat/stream - 推流完成
  返回客户端诊疗方案 (200 OK)
  处理时间: 12.3 秒

  推流事件统计:
  - Thought 迭代: 2 次
  - Action 执行: 2 次
  - Tool 调用: 2 次 (总耗时: 3.2s)
  - 多 Agent 共识: 3 个 Agent
  - 最终诊断: 已生成

════════════════════ 推流过程结束 ════════════════════
```

---

## 🔧 服务状态检查

启动后，可以访问以下地址检验服务是否就绪：

```bash
# 一键检查所有服务
curl http://localhost:8080/api/v1/file/health && echo "✓ Java 后端"
curl http://localhost:8000/health && echo "✓ LangChain"
curl http://localhost:8001/health && echo "✓ OCR 服务"
```

或者在浏览器中访问：

- **前端**: http://localhost:3000
- **Java 后端 Swagger API**: http://localhost:8080/swagger-ui.html
- **LangChain 文档**: http://localhost:8000/docs
- **OCR 文档**: http://localhost:8001/docs

---

## 📱 测试诊断流程

### 1️⃣ 上传化验单

```bash
curl -X POST http://localhost:8080/api/v1/file/upload-report \
  -F "file=@laboratory_report.pdf" \
  -H "Authorization: Bearer your_jwt_token"
```

### 2️⃣ 启动诊断（推流模式）

```bash
curl -X POST http://localhost:8080/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_jwt_token" \
  -d '{
    "query": "请分析这份化验单并给出综合诊断建议",
    "file_id": "xyz123",
    "enable_streaming": true
  }' \
  --stream
```

**实时推流输出** (Server-Sent Events 格式):

```
data: {"phase":"thought","iteration":1,"content":"分析患者指标..."}
data: {"phase":"action","tool":"check_renal_function","input":{...}}
data: {"phase":"observation","result":"肾脏GFR异常..."}
data: {"phase":"thought","iteration":2,"content":"需要进一步检查..."}
data: {"phase":"conclusion","diagnosis":"CKD 2-3期","confidence":0.86}
```

---

## 🛑 停止和清理

### 暂停服务（数据保留）

```bash
docker compose -f infrastructure/docker-compose.yml stop
```

### 完全停止（删除容器）

```bash
docker compose -f infrastructure/docker-compose.yml down
```

### 删除所有数据（包括数据库）

```bash
docker compose -f infrastructure/docker-compose.yml down -v
```

---

## 🔍 常见问题排查

### 问: 推流日志没有显示怎么办？

**解:** 检查是否已连接到推流端点：

```bash
# 查看实时日志
docker compose -f infrastructure/docker-compose.yml logs -f java-backend python-langchain

# 检查服务状态
docker compose -f infrastructure/docker-compose.yml ps
```

### 问: 容器启动失败？

**解:** 检查 .env 配置：

```bash
# 验证 .env 文件
cat .env | grep -E "(API_KEY|DATABASE|PORT)"

# 查看错误日志
docker compose -f infrastructure/docker-compose.yml logs --tail=50
```

### 问: 网络无法连接到 LLM API？

**解:** 检查 API 密钥和网络：

```bash
# 测试网络连接
docker exec medlab-langchain ping api.openai.com

# 验证 API KEY
docker exec medlab-langchain env | grep API_KEY
```

---

## 💾 日志位置

所有日志都会保存到本地：

```
infrastructure/
├── uploads/                    # 上传的化验单文件
│   └── *.pdf
├── logs/
│   ├── java-backend.log       # Java 应用日志
│   ├── python-langchain.log   # LangChain 日志
│   └── python-ocr.log         # OCR 服务日志
```

---

## ⚡ 性能监控

在启动期间查看资源使用：

```bash
# 监控 Docker 容器资源
docker stats

# 查看特定容器
docker stats medlab-java-backend medlab-langchain medlab-ocr
```

---

## 📊 完整架构流程图

```
用户上传化验单 (PDF/图片)
    ↓
[Java 后端] /api/v1/file/upload-report
    ↓
[OCR 服务] 视觉识别
    ↓
[IndicatorGAT] 指标关联图推理
    ↓
[ExpertGAT] 专家协作图推理
    ↓
[权重掩码生成] 科室优先级排序
    ↓
[ReAct 循环] Thought → Action → Observation
    ├─[LangChain Agent] 思考
    ├─[工具调用] 执行医学查询
    └─[结果反馈] 迭代分析
    ↓
[多 Agent 共识]
    ├─[专家提案] 肾脏科、消化科等
    ├─[交叉批评] 互相审查
    └─[共识决策] 综合诊疗方案
    ↓
[推流返回客户端]
    └─→ 前端 UI 展示
```

---

## 🎯 验证推流是否工作

最快验证方法：

```bash
# 终端 1: 启动服务
docker compose -f infrastructure/docker-compose.yml up --build

# 终端 2: 发送诊断请求
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "请分析化验单",
    "ocr_result": {"Cr": 130, "BUN": 15}
  }' \
  --stream

# 在终端 1 应该看到详细的推流日志输出
```

---

**🎉 启动成功后，所有诊疗流程的详细日志都会在终端实时显示！**
