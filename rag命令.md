下面给你一套“删除项目内向量库并重建”的完整 PowerShell 流程，目标目录就是：

`E:\xiangmu\dachuang\langchain_service\knowledge\vector_db`

只复制代码块里的内容执行，不要复制代码块外文字。

```powershell
# 1) 停掉当前 8001 服务
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*uvicorn main:app*8001*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Sleep -Seconds 2


# 2) 进入服务目录
Set-Location E:\xiangmu\dachuang\langchain_service


# 3) 明确指定“项目内向量库路径”
$vectorDbPath = "E:\xiangmu\dachuang\langchain_service\knowledge\vector_db"
$env:VECTOR_DB_PATH = $vectorDbPath
$env:RAG_LOCAL_EMBEDDING_PATH = "E:\xiangmu\dachuang\models\bce-embedding-base_v1"
$env:RAG_EMBEDDING_DEVICE = "cpu"

Write-Host "当前 VECTOR_DB_PATH = $env:VECTOR_DB_PATH"


# 4) 删除旧的项目内向量库
if ($vectorDbPath -ne "E:\xiangmu\dachuang\langchain_service\knowledge\vector_db") {
    throw "vectorDbPath 不符合预期，已停止，避免误删"
}

if (Test-Path $vectorDbPath) {
    Remove-Item -LiteralPath $vectorDbPath -Recurse -Force
}

New-Item -ItemType Directory -Path $vectorDbPath -Force | Out-Null


# 5) 用 bce-embedding-base_v1 重新构建向量库
& "E:\apps\Miniconda\Library\bin\conda.bat" run -n medlab-langchain python -m knowledge.build_vectorstore


# 6) 查看重建结果
Get-ChildItem -Recurse $vectorDbPath | Select-Object FullName,Length,LastWriteTime
```

如果上面执行成功，接着用下面这段重新启动服务：

```powershell
Set-Location E:\xiangmu\dachuang\langchain_service

$env:VECTOR_DB_PATH = "E:\xiangmu\dachuang\langchain_service\knowledge\vector_db"
$env:LLM_MODEL_PATH = "E:\xiangmu\dachuang\models\Qwen2.5-7B-Instruct"
$env:RAG_LOCAL_EMBEDDING_PATH = "E:\xiangmu\dachuang\models\bce-embedding-base_v1"
$env:RAG_EMBEDDING_DEVICE = "cpu"
$env:REDIS_HOST = "127.0.0.1"
$env:LLM_USE_4BIT = "true"
$env:LLM_4BIT_QUANT_TYPE = "nf4"
$env:LLM_4BIT_USE_DOUBLE_QUANT = "true"

& "E:\apps\Miniconda\envs\medlab-langchain\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8001
```

服务启动后，开另一个 PowerShell 窗口验证：

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/health"
```

再检查它实际加载的是不是项目内向量库：

```powershell
Get-Content E:\xiangmu\dachuang\logs\langchain-service.err.log -Tail 200 |
  Select-String "Loaded vectorstore|Saved vectorstore|building from source documents|RAG retrieved docs"
```

你重点看有没有类似：

```text
Loaded vectorstore from E:\xiangmu\dachuang\langchain_service\knowledge\vector_db\main
```

如果你想，我下一条可以直接给你一份“一键完成删除、重建、启动、验证”的单文件 `rebuild_vector_db.ps1` 脚本。


---
# rag召回测试
$result = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/api/v1/agent/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{
    query = "肌酐30对不同性别和年龄的人意义是否不同？"
    user_id = "test-user-1"
    agent_type = "nephrology"
  } | ConvertTo-Json)

$result.sources | ConvertTo-Json -Depth 8
