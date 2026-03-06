@echo off
REM 前端升级脚本 - 升级 Vue 3.3 到 3.4 和 Vite 4 到 5

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo Frontend Upgrade Script
echo Vue 3.3 -^> 3.4, Vite 4 -^> 5, Node 24 -^> 20 LTS
echo ==========================================
echo.

set "FRONTEND_DIR=frontend-vue"

if not exist "%FRONTEND_DIR%" (
    echo [ERROR] frontend-vue 目录不存在！
    pause
    exit /b 1
)

cd "%FRONTEND_DIR%"

echo [INFO] 当前 Node 版本：
node -v

echo.
echo [WARNING] 推荐：Node.js 应该是 20 LTS 版本
echo [INFO] 下载地址: https://nodejs.org/
echo.

echo [INFO] 创建备份...
copy package.json package.json.backup >nul 2>&1
copy package-lock.json package-lock.json.backup >nul 2>&1
echo [OK] 备份完成

echo.
echo [INFO] 正在升级依赖...
echo.

REM 升级主要依赖
echo [INFO] 升级 Vue...
call npm install vue@latest --save --legacy-peer-deps

echo [INFO] 升级 Vite...
call npm install vite@latest --save-dev --legacy-peer-deps

echo [INFO] 升级其他依赖...
call npm install vue-router@latest axios@latest pinia@latest --save --legacy-peer-deps

echo [INFO] 升级开发依赖...
call npm install "@vitejs/plugin-vue@latest" --save-dev --legacy-peer-deps

echo.
echo [INFO] 运行完整更新...
call npm update --legacy-peer-deps

if errorlevel 1 (
    echo.
    echo [ERROR] 升级过程中出现错误
    echo [INFO] 恢复备份...
    copy package.json.backup package.json >nul 2>&1
    copy package-lock.json.backup package-lock.json >nul 2>&1
    call npm install
    cd ..
    pause
    exit /b 1
)

echo.
echo ==========================================
echo 升级完成！
echo ==========================================
echo.
echo [INFO] 升级版本：
node -v
npm -v
echo.
call npm list vue vite --depth=0
echo.

echo [INFO] 备份保存在：
echo   - package.json.backup
echo   - package-lock.json.backup
echo.

echo [NEXT STEP] 测试：
echo   npm run dev
echo   npm run build
echo.

cd ..
pause
