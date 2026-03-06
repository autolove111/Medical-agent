@echo off
REM MedLabAgent System - Full Build & Start
REM 完整构建并启动前后端

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo MedLabAgent System - Full Build and Start
echo ==========================================
echo.

set "ROOT_DIR=%cd%"

REM 检查Maven
where mvn >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Maven 未安装或不在PATH中
    pause
    exit /b 1
)

REM 检查Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js 未安装或不在PATH中
    pause
    exit /b 1
)

echo [OK] Maven 和 Node.js 已安装
echo.

REM ========== 构建后端 ==========
echo [INFO] 开始构建后端...
echo.

cd /d "%ROOT_DIR%\backend-java"
call mvn clean package -DskipTests -q
if errorlevel 1 (
    echo [ERROR] 后端构建失败！
    pause
    exit /b 1
)

echo [OK] 后端构建完成
echo.

REM ========== 准备前端 ==========
echo [INFO] 检查前端依赖...
echo.

cd /d "%ROOT_DIR%\frontend-vue"
if not exist "node_modules" (
    echo [INFO] 安装前端依赖...
    call npm install -q
    if errorlevel 1 (
        echo [ERROR] 前端依赖安装失败！
        pause
        exit /b 1
    )
    echo [OK] 前端依赖已安装
) else (
    echo [OK] 前端依赖已存在
)

echo.

REM ========== 启动服务 ==========
echo [INFO] 启动服务...
echo.

timeout /t 1

REM 启动后端
cd /d "%ROOT_DIR%\backend-java"
start "MedLabAgent Backend" cmd.exe /c "title MedLabAgent Backend & echo. & echo ========== Backend Service ========== & echo. & set SPRING_PROFILES_ACTIVE=h2 & java -jar target\medlab-agent-system-1.0.0.jar & pause"

timeout /t 3

REM 启动前端
cd /d "%ROOT_DIR%\frontend-vue"
start "MedLabAgent Frontend" cmd.exe /c "title MedLabAgent Frontend & echo. & echo ========== Frontend Dev Server ========== & echo. & npm run dev & pause"

echo.
echo [SUCCESS] 构建和启动完成！
echo.
echo [INFO] 服务地址：
echo   前端: http://localhost:5173/
echo   后端: http://localhost:8080/
echo.
pause
