@echo off
REM 快速启动 LangChain 服务
REM 用于测试和诊断

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo LangChain 服务 - 快速启动
echo ==========================================
echo.

REM 进入目录
cd /d "%~dp0"

echo [1/5] 检查 Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python 不可用
    echo.
    echo 请检查：
    echo   1. Python 是否正确安装
    echo   2. 是否使用了 MSYS2 的 Python（使用标准 Python 安装）
    echo.
    pause
    exit /b 1
)

echo.
echo [2/5] 检查 pip...
python -m pip --version
if errorlevel 1 (
    echo [WARNING] pip 不可用，尝试修复...
    python -m ensurepip --upgrade 2>nul
    if errorlevel 1 (
        echo [WARNING] ensurepip 失败，尝试使用 py 启动器...
        py -3 --version >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] 无法修复 pip，Python 安装可能不完整
            echo.
            echo 请检查 IMMEDIATE_ACTION.md 进行完整诊断
            pause
            exit /b 1
        ) else (
            echo [INFO] 改用 py -3 启动器
            set "PIP_CMD=py -3 -m pip"
        )
    ) else (
        echo [OK] pip 已修复
        set "PIP_CMD=python -m pip"
    )
) else (
    echo [OK] pip 可用
    set "PIP_CMD=python -m pip"
)

echo.
echo [3/5] 验证 pip 功能...
%PIP_CMD% --version
if errorlevel 1 (
    echo [ERROR] pip 验证失败
    pause
    exit /b 1
)

echo.
echo [4/5] 运行诊断...
echo.
python diagnose.py
if errorlevel 1 (
    echo.
    echo [ERROR] 诊断发现问题
    echo 请解决上述问题后重试
    pause
    exit /b 1
)

echo.
echo [5/5] 启动服务...
echo.
echo 即将启动服务，日志将显示在下方：
echo ========== LangChain 服务日志 ==========
echo.

python main.py

echo.
