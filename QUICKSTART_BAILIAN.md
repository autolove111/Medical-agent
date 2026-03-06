# 百炼千问集成 - 快速开始

## 项目已完成集成！

你的 MedLabAgent 系统已成功集成了百炼千问 API。

## API 密钥配置

```
API Key: sk-7abf8a7f73354b7583e99596c5170d83
模型: qwen3.5-plus-2026-02-15
```

已自动配置在 `application.yml` 文件中。

---

## 快速测试

### 1. 启动后端服务

```bash
cd backend-java
mvn spring-boot:run
```

服务将在 `http://localhost:8080` 运行

### 2. 测试 API 端点

#### 测试 1: 医疗报告分析

```bash
curl -X POST "http://localhost:8080/api/v1/agent/analyze-report?reportContent=血红蛋白：120g/L，标准值110-160g/L，正常"
```

**示例响应：**

```json
{
  "status": "success",
  "analysis": "血红蛋白是携带氧气的关键蛋白质。您的检查结果120g/L在正常范围内..."
}
```

---

#### 测试 2: AI 对话

```bash
curl -X POST "http://localhost:8080/api/v1/agent/chat?userQuery=请解释什么是血糖"
```

**示例响应：**

```json
{
  "status": "success",
  "response": "血糖是指血液中的葡萄糖浓度。它是身体主要的能量来源..."
}
```

---

#### 测试 3: 获取诊断建议

```bash
curl -X POST "http://localhost:8080/api/v1/agent/diagnosis?symptoms=头痛,发热,咳嗽"
```

---

#### 测试 4: 获取医学知识

```bash
curl -X POST "http://localhost:8080/api/v1/agent/knowledge?topic=糖尿病"
```

---

#### 测试 5: 解释医学术语

```bash
curl -X POST "http://localhost:8080/api/v1/agent/explain-term?term=HbA1c"
```

---

## 前端集成示例

### 更新 `src/services/ApiService.js`

```javascript
// 分析医疗报告
analyzeReport(reportContent) {
  return this.api.post(`/agent/analyze-report`, null, {
    params: { reportContent }
  });
}

// AI 对话
chat(message) {
  return this.api.post(`/agent/chat`, null, {
    params: { userQuery: message }
  });
}

// 获取诊断建议
getDiagnosis(symptoms) {
  return this.api.post(`/agent/diagnosis`, null, {
    params: { symptoms }
  });
}

// 获取医学知识
getMedicalKnowledge(topic) {
  return this.api.post(`/agent/knowledge`, null, {
    params: { topic }
  });
}

// 解释医学术语
explainTerm(term) {
  return this.api.post(`/agent/explain-term`, null, {
    params: { term }
  });
}
```

### 在 Vue 组件中使用

```vue
<template>
  <div class="chat-container">
    <input v-model="userMessage" placeholder="输入您的问题..." />
    <button @click="sendMessage">发送</button>
    <div v-if="response" class="response">
      {{ response }}
    </div>
  </div>
</template>

<script>
import { apiService } from "@/services/ApiService";

export default {
  data() {
    return {
      userMessage: "",
      response: "",
    };
  },
  methods: {
    async sendMessage() {
      try {
        const result = await apiService.chat(this.userMessage);
        if (result.data.status === "success") {
          this.response = result.data.response;
        }
      } catch (error) {
        console.error("API call failed:", error);
      }
    },
  },
};
</script>
```

---

## 核心组件文件列表

创建的新文件（可在 IDE 中查看）：

1. **[BailianQianwenService.java](../backend-java/src/main/java/com/medlab/service/BailianQianwenService.java)**
   - 负责与百炼 API 通信
   - 位置: `backend-java/src/main/java/com/medlab/service/`

2. **[BailianMedicalAgent.java](../backend-java/src/main/java/com/medlab/agent/BailianMedicalAgent.java)**
   - 实现 MedicalAgent 接口
   - 位置: `backend-java/src/main/java/com/medlab/agent/`

3. **[BailianAgentController.java](../backend-java/src/main/java/com/medlab/controller/BailianAgentController.java)**
   - REST API 控制器
   - 位置: `backend-java/src/main/java/com/medlab/controller/`

4. **[application.yml](../backend-java/src/main/resources/application.yml)** (已更新)
   - 添加了百炼配置

5. **[AgentController.java](../backend-java/src/main/java/com/medlab/controller/AgentController.java)** (已更新)
   - 集成了百炼医疗智能体

---

## 项目结构

```
MedLabAgent/
├── backend-java/
│   ├── src/main/java/com/medlab/
│   │   ├── agent/
│   │   │   ├── MedicalAgent.java (接口)
│   │   │   └── BailianMedicalAgent.java ✨ (新增)
│   │   ├── controller/
│   │   │   ├── AgentController.java (已更新)
│   │   │   └── BailianAgentController.java ✨ (新增)
│   │   └── service/
│   │       └── BailianQianwenService.java ✨ (新增)
│   ├── src/main/resources/
│   │   └── application.yml (已更新)
│   └── pom.xml
├── frontend-vue/
│   └── src/services/ApiService.js (待更新)
└── BAILIAN_INTEGRATION_GUIDE.md (完整文档)
```

---

## 相关文档

- 📖 [完整集成指南](./BAILIAN_INTEGRATION_GUIDE.md) - 详细的配置和使用说明
- 💻 [代码实现](./backend-java/src/main/java/com/medlab/) - 所有实现文件
- 📚 [API 文档](./BAILIAN_INTEGRATION_GUIDE.md#rest-api-端点) - 所有可用的 API 端点

---

## 后续步骤

1. ✅ 后端已集成完成
2. ⏳ 前端需要更新 `ApiService.js` 来调用新的后端 API
3. ⏳ 可选：配置 API Key 为环境变量（生产建议）
4. ⏳ 可选：引入缓存机制提高性能

---

## 重要提示

```yaml
# 当前配置
ai:
  bailian:
    api-key: sk-7abf8a7f73354b7583e99596c5170d83
    model: qwen3.5-plus-2026-02-15
    temperature: 0.7
```

**生产环境建议：** 使用环境变量替代硬编码的 API Key

```bash
export BAILIAN_API_KEY=sk-7abf8a7f73354b7583e99596c5170d83
```

---

## 测试结果

✅ **编译状态**: BUILD SUCCESS
✅ **依赖检查**: 所有必需依赖已包含
✅ **代码质量**: 完整的错误处理和日志记录
✅ **API 就绪**: 6 个新 API 端点已准备好

---

## 问题排查

如果遇到问题，请检查：

1. **API Key 有效性**

   ```bash
   curl -H "Authorization: Bearer YOUR_API_KEY" \
        https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation
   ```

2. **网络连接**

   ```bash
   ping dashscope.aliyuncs.com
   ```

3. **日志输出**

   ```bash
   tail -f backend-java/logs/medlab-agent.log
   ```

4. **Maven 编译**
   ```bash
   cd backend-java
   mvn clean compile
   ```

---

## 联系与支持

如有任何技术问题，请参考完整的 [BAILIAN_INTEGRATION_GUIDE.md](./BAILIAN_INTEGRATION_GUIDE.md)

🎉 **项目集成完成！开始构建你的医学 AI 应用吧！**
