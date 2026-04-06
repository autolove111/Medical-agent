# Docker 一键启动速记卡

## 🚀 最快启动方式（复制粘贴）

### Windows

```powershell
cd d:\Users\xiaoli\Desktop\MedLabAgent
docker compose -f infrastructure/docker-compose.yml --env-file .env up --build
```

### Linux/macOS

```bash
cd ~/path/to/MedLabAgent
docker compose -f infrastructure/docker-compose.yml --env-file .env up --build
```

---

## 📡 会看到的推流日志

启动后，终端会显示**三个服务的实时日志混合流**：

```
[java-backend] ✓ 应用启动成功
[python-langchain] ✓ LangChain Agent 就绪
[python-ocr] ✓ OCR 视觉服务就绪

... 诊断过程推流 ...

[python-langchain] [ReAct Thought #1] 分析患者检验指标...
[python-langchain] [ReAct Action] 调用check_renal_function工具
[python-ocr] 执行医学知识查询...
[python-langchain] [ReAct Observation] 肾脏GFR异常
[java-backend] 推流完成，返回诊疗方案
```

---

## 🌐 服务地址

| 服务      | 地址                                  | 说明         |
| --------- | ------------------------------------- | ------------ |
| 前端 UI   | http://localhost:3000                 | Vue 应用     |
| Java API  | http://localhost:8080/swagger-ui.html | 后端接口文档 |
| LangChain | http://localhost:8000/docs            | 诊疗引擎文档 |
| OCR       | http://localhost:8001/docs            | 视觉识别文档 |
| 数据库    | localhost:5432                        | PostgreSQL   |
| 缓存      | localhost:6379                        | Redis        |

---

## ⏹️ 停止和清理

| 命令                                                          | 说明           |
| ------------------------------------------------------------- | -------------- |
| `docker compose -f infrastructure/docker-compose.yml stop`    | 暂停服务       |
| `docker compose -f infrastructure/docker-compose.yml down`    | 停止并删除容器 |
| `docker compose -f infrastructure/docker-compose.yml down -v` | 删除所有含数据 |
| `docker compose -f infrastructure/docker-compose.yml logs -f` | 查看所有日志   |

---

## 🧪 快速测试

### 1. 检查服务健康

```bash
curl http://localhost:8080/api/v1/file/health
```

### 2. 上传化验单

```bash
curl -X POST http://localhost:8080/api/v1/file/upload-report \
  -F "file=@test.pdf"
```

### 3. 启动诊断（推流）

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"请分析化验单","ocr_result":{"Cr":130,"BUN":15}}'
```

---

## 📊 完整推流流程

```
1. 用户上传化验单
   ↓
2. OCR 服务识别指标值
   ↓
3. IndicatorGAT 分析异常指标
   ↓
4. ExpertGAT 推荐相关科室
   ↓
5. ReAct 循环执行医学查询
   ├─ Thought: 思考过程
   ├─ Action: 工具调用
   └─ Observation: 结果反馈
   ↓
6. 多 Agent 共识
   ├─ 各科专家提案
   ├─ 交叉评议
   └─ 最终诊断
   ↓
7. 推流返回客户端
```

---

## ⚙️ 关键配置

编辑 `.env` 修改：

```bash
# LLM 模型选择
DASHSCOPE_MODEL=qwen3.5-plus-2026-02-15
VISION_MODEL=qwen-vl-plus

# API 密钥
DASHSCOPE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# 服务端口（如需修改）
JAVA_PORT=8080
LANGCHAIN_PORT=8000
OCR_PORT=8001
```

修改后重启：

```bash
docker compose -f infrastructure/docker-compose.yml restart
```

---

## ✅ 启动检查清单

- [ ] Docker 已安装并运行
- [ ] .env 文件存在
- [ ] API 密钥已配置（可选，有默认值）
- [ ] 端口 8080, 8000, 8001, 5432, 6379 未被占用
- [ ] 网络能访问 LLM API (测试: `ping api.openai.com`)

---

## 🔴 常见错误

| 错误                        | 原因              | 解决                                     |
| --------------------------- | ----------------- | ---------------------------------------- |
| `couldn't find env file`    | .env 路径错误     | 确保在项目根目录                         |
| `port already in use`       | 端口被占用        | 修改 .env 中的端口                       |
| `BuildFailed`               | Dockerfile 不存在 | 确保文件完整：backend-java/Dockerfile 等 |
| `API connection failed`     | 网络/API KEY 问题 | 检查 .env 中的 API_KEY 是否正确          |
| `database connection error` | 数据库未启动      | 等待 PostgreSQL 启动（1-2分钟）          |

---

## 📚 详细文档位置

- 完整启动指南: `DOCKER_QUICK_START.md`
- 推流日志详解: `DOCKER_STREAMING_GUIDE.md`
- 架构文档: `思路.md`
- 优化方案: `优化.md`

---

## 💡 一句话总结

```bash
# Windows
cd d:\Users\xiaoli\Desktop\MedLabAgent && docker compose -f infrastructure/docker-compose.yml --env-file .env up --build

# Linux/Mac
cd ~/MedLabAgent && docker compose -f infrastructure/docker-compose.yml --env-file .env up --build

# 然后在终端看实时推流日志 ✅
```

---

**🎉 启动后，所有诊疗流程都会在终端以推流方式实时展示！**
