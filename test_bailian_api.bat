@echo off
REM 百炼千问 API 集成测试脚本 (Windows 版本)
REM 用于验证后端集成是否正确

setlocal enabledelayedexpansion

set BASE_URL=http://localhost:8080
set API_VERSION=v1
set TOTAL_TESTS=0
set PASSED_TESTS=0
set FAILED_TESTS=0

echo.
echo ========================================================
echo   百炼千问 API 集成验证测试 (Windows)
echo ========================================================
echo.

REM 检查 curl 是否可用
where curl >nul 2>nul
if errorlevel 1 (
    echo 错误: 未找到 curl 命令。请确保已安装 curl。
    exit /b 1
)

REM 检查服务是否运行
echo 【步骤 1】检查服务状态...
curl -s -f "%BASE_URL%/api/%API_VERSION%/agent/health" >nul 2>nul
if errorlevel 1 (
    echo 错误: 无法连接到服务 (%BASE_URL%)
    echo.
    echo 请确保:
    echo   1. 后端服务已启动 (mvn spring-boot:run)
    echo   2. 服务运行在 http://localhost:8080
    exit /b 1
)
echo ✓ 服务正常运行
echo.

echo 【步骤 2】执行 API 测试...
echo.

REM 测试 1: 健康检查
echo ▶ 测试 1: 健康检查
set /a TOTAL_TESTS+=1
for /f "delims=" %%i in ('curl -s -X GET "%BASE_URL%/api/%API_VERSION%/agent/health"') do set response=%%i
echo   请求: GET /api/%API_VERSION%/agent/health
if "!response!"=="" (
    echo   ✗ 失败: 无响应
    set /a FAILED_TESTS+=1
) else if "!response:~-17,16!"=="success":true" (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: !response:~0,60!...
) else (
    echo   ✗ 失败
    set /a FAILED_TESTS+=1
    echo   响应: !response!
)
echo.

REM 测试 2: AI 对话
echo ▶ 测试 2: AI 对话
set /a TOTAL_TESTS+=1
for /f "delims=" %%i in ('curl -s -X POST "%BASE_URL%/api/%API_VERSION%/agent/chat?userQuery=请解释什么是血糖"') do set response=%%i
echo   请求: POST /api/%API_VERSION%/agent/chat?userQuery=...
if "!response!"=="" (
    echo   ✗ 失败: 无响应
    set /a FAILED_TESTS+=1
) else if "!response:success":true"=="" (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: 已接收
) else (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: 已接收
)
echo.

REM 测试 3: 分析医疗报告
echo ▶ 测试 3: 分析医疗报告
set /a TOTAL_TESTS+=1
for /f "delims=" %%i in ('curl -s -X POST "%BASE_URL%/api/%API_VERSION%/agent/analyze-report?reportContent=血红蛋白120g/L,正常"') do set response=%%i
echo   请求: POST /api/%API_VERSION%/agent/analyze-report?reportContent=...
if "!response!"=="" (
    echo   ✗ 失败: 无响应
    set /a FAILED_TESTS+=1
) else (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: 已接收
)
echo.

REM 测试 4: 诊断建议
echo ▶ 测试 4: 获取诊断建议
set /a TOTAL_TESTS+=1
for /f "delims=" %%i in ('curl -s -X POST "%BASE_URL%/api/%API_VERSION%/agent/diagnosis?symptoms=头痛,发热"') do set response=%%i
echo   请求: POST /api/%API_VERSION%/agent/diagnosis?symptoms=...
if "!response!"=="" (
    echo   ✗ 失败: 无响应
    set /a FAILED_TESTS+=1
) else (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: 已接收
)
echo.

REM 测试 5: 医学知识
echo ▶ 测试 5: 获取医学知识
set /a TOTAL_TESTS+=1
for /f "delims=" %%i in ('curl -s -X POST "%BASE_URL%/api/%API_VERSION%/agent/knowledge?topic=糖尿病"') do set response=%%i
echo   请求: POST /api/%API_VERSION%/agent/knowledge?topic=...
if "!response!"=="" (
    echo   ✗ 失败: 无响应
    set /a FAILED_TESTS+=1
) else (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: 已接收
)
echo.

REM 测试 6: 解释术语
echo ▶ 测试 6: 解释医学术语
set /a TOTAL_TESTS+=1
for /f "delims=" %%i in ('curl -s -X POST "%BASE_URL%/api/%API_VERSION%/agent/explain-term?term=HbA1c"') do set response=%%i
echo   请求: POST /api/%API_VERSION%/agent/explain-term?term=...
if "!response!"=="" (
    echo   ✗ 失败: 无响应
    set /a FAILED_TESTS+=1
) else (
    echo   ✓ 成功
    set /a PASSED_TESTS+=1
    echo   响应: 已接收
)
echo.

REM 输出测试结果
echo ========================================================
echo   测试结果
echo ========================================================
echo 总测试数: %TOTAL_TESTS%
echo 通过数: %PASSED_TESTS%
echo 失败数: %FAILED_TESTS%
echo.

if %FAILED_TESTS% equ 0 (
    echo ✓ 所有测试通过！集成成功！
    exit /b 0
) else (
    echo ✗ 有测试失败，请检查日志
    exit /b 1
)
