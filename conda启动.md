按现在这版仓库，直接这样启动。

先建环境：

```powershell
Set-Location E:\项目\大创实验
& "E:\apps\Miniconda\Library\bin\conda.bat" env create -f langchain_service\environment.yml
& "E:\apps\Miniconda\Library\bin\conda.bat" env create -f ai-services-python\ocr_service\environment.yml
```

如果环境已经建过，就跳过上面两条。

终端 1 启动 OCR：

```powershell
Set-Location E:\项目\大创实验\ai-services-python\ocr_service
& "E:\apps\Miniconda\Library\bin\conda.bat" run -n medlab-ocr python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

终端 2 启动 LangChain + RAG：

```powershell
Set-Location E:\项目\大创实验\langchain_service
$env:LLM_MODEL_PATH="E:\项目\大创实验\models\Qwen2.5-0.5B-Instruct"
$env:RAG_LOCAL_EMBEDDING_PATH="E:\项目\大创实验\models\bce-embedding-base_v1"
$env:REDIS_HOST="127.0.0.1"
$env:OCR_SERVICE_URL="http://127.0.0.1:8001"
& "E:\apps\Miniconda\Library\bin\conda.bat" run -n medlab-langchain python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

启动后先验证：

```powershell
curl http://127.0.0.1:8001/api/v1/health
curl http://127.0.0.1:8000/docs
curl http://127.0.0.1:8000/health
```

有两个前置条件你要自己确认：

- `Redis` 要先在本机 `127.0.0.1:6379` 跑着
- 如果当前代码强依赖数据库，`PostgreSQL` 也要在本机跑着

如果你执行后报错，把 **环境创建输出** 或 **uvicorn 启动日志** 贴给我，我继续往下压。