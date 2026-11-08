# syntax=docker/dockerfile:1.7
# 多阶段构建：builder 负责安装依赖 + 类型检查 + 打包，runtime 只保留 nginx 与静态产物

FROM node:24-alpine AS builder
WORKDIR /app

# 通过 Corepack 使用 package.json 中固定的 pnpm 版本，保证本地、CI 与镜像内行为一致
RUN corepack enable && corepack prepare pnpm@10.18.0 --activate
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

# 先只复制依赖清单：源码改动不会让依赖层失效，可最大化复用构建缓存
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# cache mount 把 pnpm store 挂在构建缓存上：
# 1) 重复构建可复用已下载的包，显著缩短安装时间；
# 2) store 不写进镜像层，避免把下载缓存带进最终产物。
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir=/pnpm/store --registry=https://registry.npmmirror.com

COPY . .

# 构建期变量注入：.dockerignore 已排除本地 .env 文件，镜像构建不应依赖开发机配置。
# ARG 在 RUN 阶段不可直接读取，需转成 ENV 才能被 check-env.mjs / Vite 读到。
ARG VITE_APP_ENV=production
ARG VITE_APP_TITLE=Agent Analytics
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_AGENT_BASE_URL=/agent/api/v1
ARG VITE_API_TIMEOUT=10000
ARG VITE_USE_MOCK=false
# 生成式 UI 开关与 Agent 的 OPENUI_ENABLED 必须同步，默认关闭
ARG VITE_OPENUI_ENABLED=false
ENV VITE_APP_ENV=${VITE_APP_ENV} \
    VITE_APP_TITLE=${VITE_APP_TITLE} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_AGENT_BASE_URL=${VITE_AGENT_BASE_URL} \
    VITE_API_TIMEOUT=${VITE_API_TIMEOUT} \
    VITE_USE_MOCK=${VITE_USE_MOCK} \
    VITE_OPENUI_ENABLED=${VITE_OPENUI_ENABLED}

# 构建期硬校验：把缺失/错误/疑似敏感的环境变量拦截在镜像之外，而不是等上线才暴露。
# pnpm build 内含 tsc 类型检查，因此镜像内同时完成类型门禁。
RUN pnpm check:env --mode production && pnpm build

FROM nginx:stable-alpine AS runtime

# nginx 官方镜像启动时会用 envsubst 渲染 /etc/nginx/templates/*.template
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

# 上游地址在后端服务名/端口变化时只需改环境变量，无需重新构建镜像
ENV BACKEND_UPSTREAM=http://application-service:8080 \
    AGENT_UPSTREAM=http://agent-service:8000 \
    ADMIN_UPSTREAM=http://admin:80

EXPOSE 80

# alpine 自带 wget，直接命中 nginx 的 /healthz
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
