@echo off
REM MedLabAgent System - Quick Start Script (Windows)
REM 快速启动所有服务

echo.
echo ==========================================
echo MedLabAgent System - Quick Start
echo ==========================================
echo.

REM 检查 Docker 和 Docker Compose
docker --version >nul 2>&1
if errorlevel 1 (
    echo Warning: Docker is not installed or not in PATH
    exit /b 1
)

docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo Warning: Docker Compose is not installed or not in PATH
    exit /b 1
)

echo ^[OK^] Docker and Docker Compose are installed
echo.

REM 进入 infrastructure 目录
cd infrastructure

echo ^[INFO^] Starting all services...
echo.

REM 启动服务
docker-compose up -d

echo.
echo ^[OK^] All services have been started
echo.

REM 等待服务就绪
echo ^[INFO^] Waiting for services to be ready...
timeout /t 10

echo.
echo ^[INFO^] Service Status:
docker-compose ps

echo.
echo ^[SUCCESS^] MedLabAgent System is running!
echo.
echo ^[INFO^] Service URLs:
echo   Backend API:     http://localhost:8080/api/v1/health
echo   Database:        localhost:5432
echo   Redis:           localhost:6379
echo   Ollama:          http://localhost:11434
echo   OCR Service:     http://localhost:8000/health
echo.
echo ^[TIPS^]
echo   View logs:       docker-compose logs -f backend
echo   Stop services:   docker-compose down
echo   Restart:         docker-compose restart
echo.
pause
