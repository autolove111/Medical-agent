# MedLabAgent 快速启动指南

## 目录

- [初次使用](#初次使用)
- [日常开发](#日常开发)
- [常见问题](#常见问题)
- [脚本说明](#脚本说明)

---

## 初次使用

### 第一次启动前后端

**方案 1: 完整构建（推荐首次使用）**

```bash
build-and-start.bat
```

这个脚本会：

1. 编译后端 Java 代码（Maven）
2. 检查并安装前端依赖（npm）
3. 自动在两个新窗口启动前后端

**耗时:** 约 1-2 分钟（取决于网络和机器配置）

---

## 日常开发

### 快速启动（日常使用）

```bash
quick-start.bat
```

这个脚本会：

- 直接使用已编译的 JAR 文件
- 快速启动前后端（无需重新编译）

**耗时:** 10-15 秒 ⚡

> **前提:** 后端已经构建过一次（已有 JAR 文件）

### 访问应用

- **前端:** [http://localhost:5173/](http://localhost:5173/)
- **后端:** [http://localhost:8080/](http://localhost:8080/)
- **H2数据库管理后台:** [http://localhost:8080/h2-console](http://localhost:8080/h2-console)

---

## 常见问题

### Q: 快速启动时提示 JAR 文件不存在

**A:** 需要先构建一次：

```bash
build-and-start.bat
```

之后就可以使用快速启动了。

### Q: 需要重新编译后端

**A:** 两个方式选择：

**方式 1: 重新构建（推荐）**

```bash
build-and-start.bat
```

**方式 2: 只构建后端**

```bash
cd backend-java
mvn clean package -DskipTests -q
```

然后用快速启动脚本启动即可。

### Q: 前端代码改了如何热重载？

**A:** 容器已经有热重载（HMR），修改 `frontend-vue/src` 中的代码会自动重新加载浏览器。

### Q: 后端代码改了如何重启？

**A:**

1. 停止服务：

```bash
stop.bat
```

2. 重新构建并启动：

```bash
build-and-start.bat
```

或手动：

```bash
cd backend-java
mvn clean package -DskipTests -q
```

然后重启服务。

### Q: 如何停止所有服务？

**A:** 运行停止脚本：

```bash
stop.bat
```

或手动关闭窗口。

---

## 脚本说明

### 📱 quick-start.bat

- **用途:** 快速启动前后端
- **前提:** 后端已编译过
- **耗时:** 10-15 秒
- **使用场景:** 日常开发、快速测试

### 🔨 build-and-start.bat

- **用途:** 完整构建并启动指

- **前提:** 无
- **耗时:** 1-2 分钟
- **使用场景:** 初次启动、后端代码大改后重建

### ⚙️ stop.bat

- **用途:** 停止所有服务
- **耗时:** 1 秒
- **使用场景:** 需要关闭服务

---

## 进阶开发

### 只启动后端

```bash
cd backend-java
set SPRING_PROFILES_ACTIVE=h2
java -jar target/medlab-agent-system-1.0.0.jar
```

### 只启动前端

```bash
cd frontend-vue
npm run dev
```

### 查看后端日志

后端窗口会实时显示日志。

### 调试后端

在 IDE（如 IntelliJ）中：

```bash
cd backend-java
mvn spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=h2"
```

---

## 性能优化建议

1. **首次使用:** 使用 `build-and-start.bat`（构建时间会因网络而异）
2. **日常开发:** 使用 `quick-start.bat`（最快)
3. **修改代码后:**
   - 前端：自动热重载，无需重启
   - 后端：停止后重新构建再启动

---

## 环境要求

- Java 11+（推荐 Java 17）
- Node.js 16+
- Maven 3.6+（如果要手动构建）
- npm或 yarn

检查版本：

```bash
java -version
node -v
npm -v
mvn -v
```
