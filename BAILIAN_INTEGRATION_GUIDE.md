# 百炼千问 API 集成说明

## 集成概述

已成功将阿里云百炼千问 API 集成到 MedLabAgent 系统中。以下是完整的集成信息：

## API 配置信息

```yaml
# 在 application.yml 中的配置：
ai:
  bailian:
    api-key: sk-7abf8a7f73354b7583e99596c5170d83
    model: qwen3.5-plus-2026-02-15
    base-url: https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation
    temperature: 0.7
    top-p: 0.95
    max-tokens: 2000
    timeout: 60000
```

## 创建的核心文件

### 1. **BailianQianwenService** (`com.medlab.service.BailianQianwenService`)

- 负责与百炼千问 API 的通信
- 处理请求体构造、响应解析、错误处理
- 提供 `generateText(prompt)` 方法调用 API

### 2. **BailianMedicalAgent** (`com.medlab.agent.BailianMedicalAgent`)

- 实现 `MedicalAgent` 接口
- 核心方法：
  - `analyzeReport(reportContent)` - 分析医疗报告
  - `chat(userQuery)` - AI对话
  - `getDiagnosisSuggestion(symptoms)` - 诊断建议
  - `getMedicalKnowledge(topic)` - 获取医学知识
  - `explainMedicalTerm(term)` - 解释医学术语

### 3. **BailianAgentController** (`com.medlab.controller.BailianAgentController`)

- 提供专用的 REST API 端点
- 位于 `/api/v1/agent` 路径下

### 4. **更新 AgentController**

- 集成百炼医疗智能体
- 更新现有端点使用真实 AI 响应

## REST API 端点

### 原有端点（已更新）

1. **分析医疗报告**

   ```
   POST /api/v1/agent/analyze-report
   参数: reportContent (string)
   返回: { status, analysis }
   ```

2. **AI对话**

   ```
   POST /api/v1/agent/chat
   参数: userQuery (string)
   返回: { status, response }
   ```

3. **获取诊断建议**
   ```
   POST /api/v1/agent/diagnosis
   参数: symptoms (string)
   返回: { status, suggestion }
   ```

### 新增端点

4. **获取医学知识**

   ```
   POST /api/v1/agent/knowledge
   参数: topic (string)
   返回: { status, knowledge }
   ```

5. **解释医学术语**

   ```
   POST /api/v1/agent/explain-term
   参数: term (string)
   返回: { status, explanation }
   ```

6. **健康检查**
   ```
   GET /api/v1/agent/health
   返回: { status, message }
   ```

## 依赖信息

项目已包含所需的所有依赖：

- **Spring Boot** 2.7.17 - Web 框架
- **Spring Data JPA** - 数据持久化
- **Lombok** 1.18.30 - 代码生成
- **Jackson** - JSON 序列化/反序列化（包含在 Spring Boot 中）

HTTP 调用通过已配置的 `RestTemplate` Bean 完成。

## 使用示例

### 1. 分析报告

```bash
curl -X POST "http://localhost:8080/api/v1/agent/analyze-report?reportContent=血红蛋白120g/L"
```

### 2. AI对话

```bash
curl -X POST "http://localhost:8080/api/v1/agent/chat?userQuery=请解释什么是血糖"
```

### 3. 诊断建议

```bash
curl -X POST "http://localhost:8080/api/v1/agent/diagnosis?symptoms=头痛,发热,咳嗽"
```

### 4. 获取医学知识

```bash
curl -X POST "http://localhost:8080/api/v1/agent/knowledge?topic=糖尿病"
```

### 5. 解释术语

```bash
curl -X POST "http://localhost:8080/api/v1/agent/explain-term?term=HbA1c"
```

## 前端集成指南

更新 `ApiService.js` 来调用新端点：

```javascript
// 医疗报告分析
async analyzeReport(reportContent) {
  return this.api.post('/agent/analyze-report', null, {
    params: { reportContent }
  });
}

// AI对话
async chat(userQuery) {
  return this.api.post('/agent/chat', null, {
    params: { userQuery }
  });
}

// 诊断建议
async getDiagnosis(symptoms) {
  return this.api.post('/agent/diagnosis', null, {
    params: { symptoms }
  });
}

// 医学知识
async getMedicalKnowledge(topic) {
  return this.api.post('/agent/knowledge', null, {
    params: { topic }
  });
}

// 解释术语
async explainTerm(term) {
  return this.api.post('/agent/explain-term', null, {
    params: { term }
  });
}
```

## 运行项目

```bash
# 编译项目
cd backend-java
mvn clean package

# 运行项目
java -jar target/medlab-agent-system-1.0.0.jar
```

## 项目结构

```
backend-java/src/main/java/com/medlab/
├── controller/
│   ├── AgentController.java (已更新)
│   └── BailianAgentController.java (新增)
├── agent/
│   ├── MedicalAgent.java (接口)
│   └── BailianMedicalAgent.java (新增-实现)
├── service/
│   └── BailianQianwenService.java (新增)
└── ...
```

## 注意事项

1. **API Key 安全性**
   - 当前 API Key 已硬编码在配置文件中
   - **生产环境建议**：使用环境变量或密钥管理系统
   - 修建议：
     ```yaml
     ai:
       bailian:
         api-key: ${BAILIAN_API_KEY}
     ```

2. **超时配置**
   - 默认超时时间为 60 秒
   - 可根据需要调整 `ai.bailian.timeout`

3. **模型选择**
   - 当前使用 `qwen3.5-plus-2026-02-15`
   - 可根据性能和成本要求选择其他模型

4. **错误处理**
   - 所有 API 调用都有完整的异常处理
   - 错误信息会返回给前端

5. **日志记录**
   - 所有关键操作都有日志记录
   - 日志级别可在 `application.yml` 中配置

## 下一步优化建议

1. 添加请求缓存机制，减少 API 调用
2. 实现流式响应（SSE），支持实时数据推送
3. 添加 API 调用监控和统计
4. 实现多轮对话历史管理
5. 添加用户反馈机制改进 AI 响应质量

## 故障排查

### 问题：API 返回 401 错误

**解决**：检查 API Key 是否有效

### 问题：API 返回 429 错误（频率限制）

**解决**：检查 API 调用频率，可能需要升级配额

### 问题：连接超时

**解决**：增加 `timeout` 配置或检查网络连接

## 支持

如有任何问题，请检查：

1. API Key 的有效性
2. 网络连接
3. 应用日志输出
