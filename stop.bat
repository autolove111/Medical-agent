@echo off
REM MedLabAgent System - Stop Services
REM 停止所有服务

echo.
echo ==========================================
echo MedLabAgent System - Stop Services
echo ==========================================
echo.

echo [INFO] 停止所有Java和Node进程...
echo.

REM 停止Java进程（后端）
taskkill /F /IM java.exe /T 2>nul
if errorlevel 1 (
    echo [INFO] 未找到运行中的Java进程
) else (
    echo [OK] 已停止后端服务
)

echo.

REM 停止Node进程（前端）
taskkill /F /IM node.exe /T 2>nul
if errorlevel 1 (
    echo [INFO] 未找到运行中的Node进程
) else (
    echo [OK] 已停止前端服务
)

echo.
echo [SUCCESS] 所有服务已停止
echo.
pause
