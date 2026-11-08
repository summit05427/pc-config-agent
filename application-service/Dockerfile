# syntax=docker/dockerfile:1.7

# ---------- 构建阶段 ----------
# 固定 Maven + JDK 21 镜像，保证本地与 CI 产出一致
FROM maven:3.9-eclipse-temurin-21-alpine AS builder

WORKDIR /build

# 先只复制构建描述文件，让依赖解析结果单独成层；源码变更时可复用该层缓存
COPY pom.xml mvnw mvnw.cmd ./
COPY .mvn/ .mvn/
RUN chmod +x mvnw

# BuildKit 缓存挂载把本地 Maven 仓库持久化，重复构建无需重新下载依赖
RUN --mount=type=cache,target=/root/.m2 \
    ./mvnw -B -ntp -DskipTests dependency:go-offline

# 源码最后复制，最大化利用上面的依赖缓存层
COPY src ./src
RUN ./mvnw -B -ntp -DskipTests package

# ---------- 运行阶段 ----------
FROM eclipse-temurin:21-jre-alpine

# 时区数据：容器默认 UTC，业务日志与数据库时间统一为 Asia/Shanghai
RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone
ENV TZ=Asia/Shanghai

# 使用固定 uid/gid 的非 root 用户运行，降低容器逃逸后的影响面
RUN addgroup -g 10001 -S app \
    && adduser -u 10001 -S -G app app

WORKDIR /app
COPY --from=builder --chown=10001:10001 /build/target/*.jar /app/app.jar

EXPOSE 8080

# 健康检查直接访问已在 SecurityConfig 放行的 actuator 端点，无需认证
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/actuator/health || exit 1

USER 10001

# MaxRAMPercentage 让 JVM 按容器内存上限的 75% 设置堆，避免被宿主机总内存误导；
# ExitOnOutOfMemoryError 让 OOM 后立即退出，交由编排系统重启，而不是留下不可用进程。
ENTRYPOINT ["java", \
    "-XX:MaxRAMPercentage=75.0", \
    "-XX:+ExitOnOutOfMemoryError", \
    "-XX:+UseContainerSupport", \
    "-Duser.timezone=Asia/Shanghai", \
    "-Dfile.encoding=UTF-8", \
    "-jar", "/app/app.jar"]
