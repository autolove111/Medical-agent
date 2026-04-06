# Docker 一键启动指南

## 🚀 快速开始

### Windows 用户

```powershell
# 方法1: 直接运行（推荐）
.\docker-run.ps1

# 方法2: 指定操作
.\docker-run.ps1 -Action start   # 启动服务
.\docker-run.ps1 -Action stop    # 停止服务
.\docker-run.ps1 -Action rm      # 删除所有数据
.\docker-run.ps1 -Action logs    # 查看日志
```

### Linux / macOS 用户

```bash
# 赋予执行权限（首次运行）
chmod +x ./docker-run.sh

# 启动服务
./docker-run.sh start

# 停止服务
./docker-run.sh stop

# 删除所有数据
./docker-run.sh rm

# 查看日志
./docker-run.sh logs
```

---

## 📡 实时推流输出说明

启动后，脚本会自动显示**三个核心服务的实时日志流**：

```
[java-backend]     2024-04-01 14:30:45.123  INFO  MedLabApplication : 应用启动完成
[python-langchain] 2024-04-01 14:30:46.456  INFO  LangChain Agent 初始化...
[python-ocr]       2024-04-01 14:30:47.789  INFO  OCR 服务就绪
```

### 日志流展示的内容

| 服务                 | 关键日志                          | 说明                 |
| -------------------- | --------------------------------- | -------------------- |
| **java-backend**     | `Creating medical agent for user` | 创建医学诊疗链       |
|                      | `Generated weight mask`           | GAT 生成权重掩码     |
|                      | `ReAct iteration #1`              | ReAct 推理循环       |
| **python-langchain** | `[ReAct Thought #1]`              | 思考阶段             |
|                      | `[ReAct Action]`                  | 行动阶段（工具调用） |
|                      | `[ReAct Observation]`             | 观察阶段             |
| **python-ocr**       | `Processing vision task`          | 处理视觉识别         |
|                      | `LLM response received`           | LLM 返回结果         |

---

## 📊 服务地址

启动完成后，可访问以下地址：

```
前端 UI              : http://localhost:3000
Java 后端 API        : http://localhost:8080/swagger-ui.html
LangChain Agent      : http://localhost:8000/docs
OCR 视觉服务         : http://localhost:8001/docs
PostgreSQL           : localhost:5432
Redis                : localhost:6379
```

---

## 🔍 测试诊断链路

### 1️⃣ 上传化验单

```bash
curl -X POST http://localhost:8080/api/v1/file/upload-report \
  -F "file=@laboratory_report.pdf" \
  -H "Authorization: Bearer your_token"

# 响应示例
{
  "file_id": "xyz123",
  "ocr_result": {
    "indicators": {
      "Cr": 130,
      "BUN": 15,
      "UA": 450
    }
  }
}
```

### 2️⃣ 启动诊断（流式输出）

```bash
curl -X POST http://localhost:8080/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{
    "query": "请分析这份化验单",
    "file_id": "xyz123"
  }'

# 实时推流输出示例
data: {"phase": "thought", "content": "患者肌酐升高..."}
data: {"phase": "action", "tool": "check_renal_function"}
data: {"phase": "observation", "result": "肾脏功能异常..."}
data: {"phase": "conclusion", "diagnosis": "..."}
```

### 3️⃣ 在终端观看推流过程

启动脚本会自动显示三个服务的日志流拼接，类似：

```
2024-04-01 14:31:00.123 [java-backend] POST /api/v1/chat/stream - 开始诊断
2024-04-01 14:31:00.456 [python-langchain] [ReAct Thought #1] 分析患者检验指标...
2024-04-01 14:31:01.123 [python-ocr] Checking kidney function...
2024-04-01 14:31:01.567 [python-langchain] [ReAct Action] 调用肾脏科工具
2024-04-01 14:31:02.234 [python-ocr] Tool result received
2024-04-01 14:31:02.890 [python-langchain] [ReAct Observation] 肾脏GFR异常
2024-04-01 14:31:03.456 [python-langchain] [ReAct Thought #2] 需要进一步检查...
2024-04-01 14:31:04.123 [java-backend] POST /api/v1/chat/stream - 诊断完成，返回结果
```

---

## 🛠️ 常见问题

### Q1: 端口被占用怎么办？

修改 `.env` 文件中的端口配置，然后重启：

```bash
# 编辑 .env
# 修改 Java 后端端口
JAVA_PORT=8081  # 改为 8081

# 重启
docker compose down
docker compose up -d --build
```

### Q2: API 密钥失效怎么办？

编辑 `.env` 文件，更新 LLM API 密钥：

```bash
DASHSCOPE_API_KEY=your_new_key
OPENAI_API_KEY=your_new_key

# 重启服务生效
docker compose restart python-langchain python-ocr
```

### Q3: 如何查看完整日志？

```bash
# 查看单个服务日志
docker compose logs python-langchain

# 跟随日志流
docker compose logs -f java-backend

# 查看特定时间范围的日志
docker compose logs --since 10m java-backend
```

### Q4: 如何清理旧数据？

```bash
# 停止并删除所有容器和卷
docker compose down -v

# 重新启动
./docker-run.ps1  # Windows
./docker-run.sh   # Linux/macOS
```

---

## 🔧 高级配置

### 修改日志级别

编辑 `.env`：

```bash
# Java 日志级别
JAVA_LOG_LEVEL=DEBUG   # 默认 INFO，改为 DEBUG 获得详细日志

# Python 日志级别
PYTHON_LOG_LEVEL=DEBUG  # 默认 INFO
```

### 启用性能监控

```bash
# 在另一个终端运行
docker stats medlab-java-backend medlab-langchain medlab-ocr
```

### 查看网络通信

```bash
# 捕获 Java 和 Python 服务之间的网络流量
docker network inspect medlab-network
```

---

## 📈 推流过程解析

完整的医学诊断推流过程：

```
1. 👤 用户上传化验单
   └─> OCR 服务处理 (python-ocr)

2. 🧠 GAT 推理
   └─> 指标关联图分析 (indicator_gat)
   └─> 专家协作图调制 (expert_gat)
   └─> 生成科室权重掩码

3. 🔄 ReAct 循环 (python-langchain)
   ├─ Thought: 思考下一步
   ├─ Action: 选择科室工具
   ├─ Observation: 收集工具结果
   └─ (重复 1-3 步，最多 5 次)

4. 👥 多 Agent 共识 (多_agent_consensus)
   ├─ 专家提议 (AgentPropose)
   ├─ 交叉批评 (AgentCriticism)
   └─ 共识决策 (ConsensusManager)

5. 📊 返回结果
   └─> 前端展示诊疗方案
```

---

## 💡 最佳实践

1. **首次启动**：留出充足时间等待所有服务启动（通常 1-2 分钟）
2. **监控日志**：始终保持日志流窗口以便快速诊断问题
3. **定期清理**：每周运行一次 `docker system prune -a` 清理未使用镜像
4. **备份数据**：生产环境前务必备份 PostgreSQL 数据库

---

## 🆘 获取支持

- 检查日志：`docker compose logs -f`
- 查看服务状态：`docker ps`
- 验证网络：`docker network inspect medlab-network`
- 健康检查：`curl http://localhost:8080/api/v1/file/health`

---

## 版本信息

- Docker Compose 版本: 3.8+
- 服务数量: 6 个（PostgreSQL、Redis、Java、Python LangChain、Python OCR、前端）
- 预期启动时间: 60-120 秒
- 最小资源需求: 4GB RAM, 2 CPU cores
