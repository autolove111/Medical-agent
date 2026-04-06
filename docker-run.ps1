# MedLabAgent Docker 一键启动脚本 (PowerShell - 简化版)
param(
    [ValidateSet('start', 'stop', 'rm', 'logs')]
    [string]$Action = 'start'
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $MyInvocation.MyCommand.Path
$InfraDir = Join-Path $ProjectRoot "infrastructure"
$EnvFile = Join-Path $ProjectRoot ".env"

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          MedLabAgent 医疗 AI 系统 Docker 启动器          ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

if ($Action -eq 'start') {
    Write-Host ""
    Write-Host "[检查] 检查运行环境..." -ForegroundColor Yellow
    
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "错误: Docker 未安装" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Docker 已安装" -ForegroundColor Green
    
    if (-not (Test-Path $EnvFile)) {
        if (Test-Path "$ProjectRoot\.env.example") {
            Copy-Item "$ProjectRoot\.env.example" $EnvFile
            Write-Host "✓ .env 文件已创建" -ForegroundColor Green
        }
    }
    
    Write-Host ""
    Write-Host "[启动] 启动所有 Docker 服务..." -ForegroundColor Yellow
    Write-Host "    - PostgreSQL"
    Write-Host "    - Redis"
    Write-Host "    - Python OCR 服务"
    Write-Host "    - Python LangChain Agent"
    Write-Host "    - Java 后端"
    Write-Host "    - Vue 前端"
    
    Push-Location $InfraDir
    
    Write-Host ""
    Write-Host "[💻] 构建镜像并启动容器..." -ForegroundColor Yellow
    docker compose --project-name medlab -f docker-compose.yml --env-file $EnvFile up -d --build
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "错误: 服务启动失败" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    
    Write-Host "✓ 服务已启动" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "[等待] 等待服务健康检查..." -ForegroundColor Yellow
    
    $attempts = 0
    $maxAttempts = 30
    while ($attempts -lt $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "✓ 服务健康检查通过" -ForegroundColor Green
                break
            }
        }
        catch { }
        
        Write-Host "  等待中... ($attempts/$maxAttempts)" -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
        $attempts++
    }
    
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║                    服务已就绪 ✓                          ║" -ForegroundColor Cyan
    Write-Host "╠════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "║" -ForegroundColor Cyan
    Write-Host "║  📱  前端 UI                : http://localhost:3000" -ForegroundColor Cyan
    Write-Host "║  🔧  Java 后端 API        : http://localhost:8080" -ForegroundColor Cyan
    Write-Host "║  🤖  LangChain Agent      : http://localhost:8000" -ForegroundColor Cyan
    Write-Host "║  👁   OCR 视觉服务         : http://localhost:8001" -ForegroundColor Cyan
    Write-Host "║  🗄   PostgreSQL           : localhost:5432" -ForegroundColor Cyan
    Write-Host "║  🔴  Redis                 : localhost:6379" -ForegroundColor Cyan
    Write-Host "║" -ForegroundColor Cyan
    Write-Host "╠════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "║  💡 启动诊断测试:                                          ║" -ForegroundColor Cyan
    Write-Host "║     1. 上传化验单 POST /api/v1/file/upload-report        ║" -ForegroundColor Cyan
    Write-Host "║     2. 启动诊断 POST /api/v1/chat                        ║" -ForegroundColor Cyan
    Write-Host "║     3. 观看下方的实时推流日志                             ║" -ForegroundColor Cyan
    Write-Host "║" -ForegroundColor Cyan
    Write-Host "║  📊 停止服务: docker compose -f docker-compose.yml down  ║" -ForegroundColor Cyan
    Write-Host "║  🗑   清理数据: docker compose -f docker-compose.yml down -v ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Host "[📡] 显示实时推流日志 (Ctrl+C 停止)..." -ForegroundColor Yellow
    Write-Host ""
    
    docker compose --project-name medlab -f docker-compose.yml logs -f --timestamps java-backend python-langchain python-ocr
    
    Pop-Location
}
elseif ($Action -eq 'stop') {
    Write-Host ""
    Write-Host "[停止] 停止所有 Docker 服务..." -ForegroundColor Yellow
    Push-Location $InfraDir
    docker compose --project-name medlab -f docker-compose.yml down
    Write-Host "✓ 服务已停止" -ForegroundColor Green
    Pop-Location
}
elseif ($Action -eq 'rm') {
    Write-Host ""
    Write-Host "[删除] 删除所有容器和数据卷..." -ForegroundColor Red
    Push-Location $InfraDir
    docker compose --project-name medlab -f docker-compose.yml down -v
    Write-Host "✓ 所有数据已删除" -ForegroundColor Green
    Pop-Location
}
elseif ($Action -eq 'logs') {
    Push-Location $InfraDir
    docker compose --project-name medlab -f docker-compose.yml logs -f
    Pop-Location
}

Write-Host ""
