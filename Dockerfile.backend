FROM maven:3.9.4-eclipse-temurin-17 AS builder

WORKDIR /build

# 复制 pom.xml 和源代码
COPY pom.xml .
COPY src ./src

# 编译项目
RUN mvn clean package -DskipTests

# 运行阶段
FROM eclipse-temurin:17-jdk-alpine

WORKDIR /app

# 从构建阶段复制编译好的JAR文件
COPY --from=builder /build/target/medlab-agent-system-1.0.0.jar app.jar

# 暴露端口
EXPOSE 8080

# 设置环境变量
ENV JAVA_OPTS="-Xmx512m -Xms256m"

# 启动应用
ENTRYPOINT ["java", "-jar", "app.jar"]
