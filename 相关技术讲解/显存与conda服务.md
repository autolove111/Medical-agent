明白了，你不需要保存成脚本，只要一组可以直接在 PowerShell 终端里**逐条复制粘贴**执行的原生命令。  

下面按排查逻辑顺序整理成可直接执行的终端命令（**无需保存文件**，一行一行复制到终端里运行即可）。

---

## 1. 看显卡显存总览

```powershell
nvidia-smi
```

## 2. 看具体哪些进程占显存（带 PID）

```powershell
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
```

## 3. 将 PID 反查成 Windows 进程名（手动替换 PID，例如 32808）

```powershell
Get-Process -Id 32808
```

## 4. 检查日志里有没有爆显存错误（替换成你的实际日志路径）

```powershell
Get-Content E:\xiangmu\dachuang\logs\langchain-service.err.log -Tail 200 | Select-String "CUDA out of memory|out of memory|OOM|RuntimeError|killed|failed"
```

## 5. 边跑边盯显存变化（每 2 秒刷新）

```powershell
while ($true) { nvidia-smi; Start-Sleep 2; Clear-Host }
```

（按 `Ctrl+C` 停止）

## 6. 查看所有 Python / uvicorn / conda 相关进程

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'python|uvicorn|conda' } | Select-Object Id,ProcessName,Path,StartTime
```

## 7. 查看更详细的命令行（包含环境、脚本路径、端口）

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -or $_.Name -like '*conda*' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine
```

## 8. 查看特定端口（比如 8001）是否在监听

```powershell
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

## 9. 查看所有监听中的端口及对应进程

```powershell
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess
```

## 10. 根据端口关服务（例如关掉 8001）

```powershell
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
```

## 11. 根据 PID 强制关进程

```powershell
Stop-Process -Id <PID> -Force
```

## 12. 查看 conda 有哪些可用环境

```powershell
conda env list
```

---

如果你希望**一次性按顺序查完**但不写脚本，可以依次复制上面的每一段命令执行。  

如果你想要更紧凑的“多命令同行执行”方式，比如用 `;` 分隔，也可以，但建议先逐条执行更清晰。