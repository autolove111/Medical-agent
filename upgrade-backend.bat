@echo off
REM 后端升级脚本 - 升级 Spring Boot 2.7 到 3.3 和 Java 11 到 17

setlocal enabledelayedexpansion

echo.
echo ==========================================
echo Backend Upgrade Script
echo Spring Boot 2.7 -^> 3.3, Java 11 -^> 17
echo ==========================================
echo.

set "POM_FILE=backend-java\pom.xml"

if not exist "%POM_FILE%" (
    echo [ERROR] pom.xml 文件不存在！
    pause
    exit /b 1
)

echo [INFO] 开始升级后端...
echo.

REM 创建备份
echo [INFO] 创建备份 pom.xml.backup...
copy "%POM_FILE%" "%POM_FILE%.backup" >nul
echo [OK] 备份完成

echo.
echo [INFO] 正在修改 pom.xml...
echo.

REM 使用 PowerShell 进行替换
powershell -Command "
    $file = '%POM_FILE%'
    $content = Get-Content $file -Raw
    
    # 替换 Spring Boot 版本
    $content = $content -replace 'version>2\.7\.\d+</version', 'version>3.3.5</version'
    
    # 替换 Java 版本
    $content = $content -replace '<java\.version>11</java\.version>', '<java.version>17</java.version>'
    
    # 提示不再需要 LangChain4j（可选）
    # 新版可能需要调整依赖
    
    Set-Content $file $content
    
    Write-Host '[OK] pom.xml 升级完成'
"

if errorlevel 1 (
    echo [ERROR] 升级失败，已自动恢复备份
    copy "%POM_FILE%.backup" "%POM_FILE%" >nul
    pause
    exit /b 1
)

echo.
echo [INFO] 正在清理并重新编译...
cd backend-java

REM 清理
mvn clean -q

REM 重新编译
echo [INFO] 编译中（这可能需要几分钟）...
mvn compile -q

if errorlevel 1 (
    echo.
    echo [ERROR] 编译失败！
    echo [INFO] 已保存备份到: %POM_FILE%.backup
    cd ..
    pause
    exit /b 1
)

echo.
echo [OK] 编译成功！

cd ..

echo.
echo ==========================================
echo 升级完成！
echo ==========================================
echo.
echo [INFO] 变更说明：
echo   - Spring Boot: 2.7.17 -^> 3.3.5
echo   - Java: 11 -^> 17
echo   - 备份: %POM_FILE%.backup
echo.
echo [NEXT STEP] 后续需要注意：
echo   1. 查看是否有编译错误
echo   2. 测试所有功能
echo   3. 如遇问题，恢复备份：copy %POM_FILE%.backup %POM_FILE%
echo.
pause
