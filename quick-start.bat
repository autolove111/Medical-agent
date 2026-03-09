@echo off
REM MedLabAgent System - Quick Start Script (No Build)
REM 快速启动前后端（无需重新编译）

setlocal enabledelayedexpansion

REM 设置 JDK 21
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo.
echo ==========================================
echo MedLabAgent System - Quick Start
echo ==========================================
echo.

REM 检查后端JAR是否存在
if not exist "backend-java\target\medlab-agent-system-1.0.0.jar" (
    echo [ERROR] 后端JAR文件不存在！
    echo [INFO] 请先运行: build-backend.bat
    pause
    exit /b 1
)

echo [OK] 准备启动前后端服务...
echo.

REM 保存当前目录
set "ROOT_DIR=%cd%"

REM 启动后端（在新窗口）
cd /d "%ROOT_DIR%\backend-java"
start "MedLabAgent Backend" cmd.exe /c "title MedLabAgent Backend & echo. & echo ========== Starting Backend ========== & echo. & java -jar target\medlab-agent-system-1.0.0.jar & pause"

timeout /t 2

REM 启动前端（在新窗口）
cd /d "%ROOT_DIR%\frontend-vue"
start "MedLabAgent Frontend" cmd.exe /c "title MedLabAgent Frontend & echo. & echo ========== Starting Frontend ========== & echo. & npm run dev & pause"

timeout /t 2

echo.
echo [SUCCESS] 启动完成！
echo.
echo [INFO] 服务地址：
echo   前端: http://localhost:5173/
echo   后端: http://localhost:8080/
echo.
echo [TIPS] 现在两个窗口应该在启动服务，请稍候...
echo.
pause
