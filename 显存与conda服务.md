# 显存、端口与 Conda 排查

这部分排查命令已整理进：

- [环境配置与部署说明.md](环境配置与部署说明.md)

常用命令保留如下：

```powershell
nvidia-smi
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv
conda env list
Get-Process | Where-Object { $_.ProcessName -match 'python|uvicorn|conda' } | Select-Object Id,ProcessName,Path,StartTime
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -or $_.Name -like '*conda*' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess
```

