#!/usr/bin/env powershell
# MedLabAgent System - Full Upgrade Script (PowerShell)
# 升级 Spring Boot 2.7->3.3, Java 11->17, Vue 3.3->3.4, Vite 4->5

param(
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# 颜色定义
$script:Colors = @{
    Success = 'Green'
    Error   = 'Red'
    Warning = 'Yellow'
    Info    = 'Cyan'
}

function Write-Info { Write-Host "[INFO] $args" -ForegroundColor $Colors.Info }
function Write-Success { Write-Host "[OK] $args" -ForegroundColor $Colors.Success }
function Write-Warning { Write-Host "[WARNING] $args" -ForegroundColor $Colors.Warning }
function Write-ErrorMsg { Write-Host "[ERROR] $args" -ForegroundColor $Colors.Error }

Clear-Host

Write-Host @"
==========================================
MedLabAgent System - Full Upgrade
==========================================

升级内容：
  后端: Spring Boot 2.7 -> 3.3, Java 11 -> 17
  前端: Vue 3.3 -> 3.4, Vite 4 -> 5
  环境: Node.js 24 -> 20 LTS（手动）

"@ -ForegroundColor Cyan

Write-Warning "警告 ⚠️"
Write-Host @"
  1. 此操作将修改 pom.xml 和 package.json
  2. 已自动创建备份
  3. 建议在测试分支进行
"@

# ========== 前置检查 ==========
Write-Host @"

==========================================
前置检查
==========================================
"@ -ForegroundColor Cyan

Write-Info "检查 Java..."
try {
    $javaVersion = java -version 2>&1 | Select-String -Pattern 'version' | Out-String
    Write-Success "Java 已安装"
}
catch {
    Write-ErrorMsg "Java 未安装"
    exit 1
}

Write-Info "检查 Maven..."
try {
    $mavenVersion = mvn -v 2>&1 | Select-String -Pattern 'Apache Maven' | Out-String
    Write-Success "Maven 已安装"
}
catch {
    Write-ErrorMsg "Maven 未安装"
    exit 1
}

Write-Info "检查 Node.js..."
try {
    $nodeVersion = node -v
    Write-Success "Node.js 已安装: $nodeVersion"
}
catch {
    Write-ErrorMsg "Node.js 未安装"
    exit 1
}

Write-Info "检查 npm..."
try {
    $npmVersion = npm -v
    Write-Success "npm 已安装: $npmVersion"
}
catch {
    Write-ErrorMsg "npm 未安装"
    exit 1
}

if (-not $Force) {
    Write-Host @"

准备开始升级...
按 Enter 继续，或 Ctrl+C 取消
"@
    Read-Host | Out-Null
}

# ========== 升级后端 ==========
Write-Host @"

==========================================
STEP 1/2: 升级后端
==========================================
"@ -ForegroundColor Cyan

$pomFile = "backend-java\pom.xml"

if (-not (Test-Path $pomFile)) {
    Write-ErrorMsg "pom.xml 文件不存在！"
    exit 1
}

Write-Info "创建备份..."
Copy-Item $pomFile "$pomFile.backup" -Force | Out-Null
Write-Success "pom.xml 已备份"

Write-Info "修改 pom.xml..."
try {
    $content = Get-Content $pomFile -Raw
    
    # 替换版本号
    $content = $content -replace '(<spring-boot-starter-parent[^>]*?version>)2\.7\.\d+', '${1}3.3.5'
    $content = $content -replace '(<java\.version>)11', '${1}17'
    $content = $content -replace '(<spring-boot-maven-plugin[^>]*?version>)2\.7\.\d+', '${1}3.3.5'
    
    Set-Content $pomFile $content -Encoding UTF8
    Write-Success "pom.xml 已更新"
}
catch {
    Write-ErrorMsg "修改 pom.xml 失败: $_"
    Copy-Item "$pomFile.backup" $pomFile -Force | Out-Null
    exit 1
}

Write-Info "清理项目..."
try {
    Push-Location "backend-java"
    mvn clean -q 2>$null
    Write-Info "重新编译（这可能需要 2-3 分钟）..."
    mvn compile -q
    Pop-Location
    Write-Success "后端编译完成"
}
catch {
    Write-ErrorMsg "后端编译失败: $_"
    Write-Warning "恢复备份..."
    Copy-Item "$pomFile.backup" $pomFile -Force | Out-Null
    exit 1
}

# ========== 升级前端 ==========
Write-Host @"

==========================================
STEP 2/2: 升级前端
==========================================
"@ -ForegroundColor Cyan

$packageFile = "frontend-vue\package.json"
$lockFile = "frontend-vue\package-lock.json"

if (-not (Test-Path $packageFile)) {
    Write-ErrorMsg "package.json 文件不存在！"
    exit 1
}

Write-Info "创建备份..."
Copy-Item $packageFile "$packageFile.backup" -Force | Out-Null
if (Test-Path $lockFile) {
    Copy-Item $lockFile "$lockFile.backup" -Force | Out-Null
}
Write-Success "前端文件已备份"

Write-Info "升级依赖（这可能需要 2-3 分钟）..."
try {
    Push-Location "frontend-vue"
    
    # 清除 node_modules 并重新安装
    if (Test-Path "node_modules") {
        Remove-Item "node_modules" -Recurse -Force | Out-Null
    }
    
    npm install | Out-Null
    npm install vue@latest vite@latest vue-router@latest axios@latest pinia@latest "@vitejs/plugin-vue@latest" --save --legacy-peer-deps -q
    
    Pop-Location
    Write-Success "前端升级完成"
}
catch {
    Write-ErrorMsg "前端升级失败: $_"
    Write-Warning "恢复备份..."
    Copy-Item "$packageFile.backup" $packageFile -Force | Out-Null
    Pop-Location
    exit 1
}

# ========== 完成 ==========
Write-Host @"

==========================================
升级完成！
==========================================

升级摘要：
  后端: Spring Boot 2.7.17 -> 3.3.5
  后端: Java 11 -> 17
  前端: Vue 3.3.4 -> 3.4.x
  前端: Vite 4.5.0 -> 5.x

备份文件：
  - backend-java/pom.xml.backup
  - frontend-vue/package.json.backup
  - frontend-vue/package-lock.json.backup

后续步骤：

1. 验证构建：
   cd backend-java
   mvn clean package -DskipTests

2. 测试前端：
   cd frontend-vue
   npm run build

3. 测试运行：
   .\\quick-start.bat

4. 如遇问题，恢复备份：
   copy backend-java\\pom.xml.backup backend-java\\pom.xml
   copy frontend-vue\\package.json.backup frontend-vue\\package.json

"@ -ForegroundColor Green

Write-Info "升级完成后建议进行 git commit"
