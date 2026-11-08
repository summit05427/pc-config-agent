# syntax=docker/dockerfile:1.7
# 多阶段构建：builder 安装依赖并打包，runtime 只保留 nginx 与静态产物

FROM node:24-alpine AS builder
WORKDIR /app

# 通过 Corepack 使用固定 pnpm 版本，保证本地、CI 与镜像内行为一致
RUN corepack enable && corepack prepare pnpm@10.18.0 --activate
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

# 先只复制依赖清单，源码改动不会让依赖层失效
COPY package.json pnpm-lock.yaml ./

RUN --mount=type=cache,id=admin-pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir=/pnpm/store --registry=https://registry.npmmirror.com

COPY . .

# 构建期变量注入。VITE_BASE_PATH=/admin/ 决定资源与路由前缀，
# 必须与 frontend Nginx 的 /admin/ 代理保持一致，否则资源会 404。
ARG VITE_APP_TITLE=Agent 管理后台
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_BASE_PATH=/admin/
ENV VITE_APP_TITLE=${VITE_APP_TITLE} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_BASE_PATH=${VITE_BASE_PATH}

# pnpm build 内含 tsc 类型检查，镜像内同时完成类型门禁
RUN pnpm build

FROM nginx:stable-alpine AS runtime

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

# alpine 自带 wget，直接命中 nginx 的 /healthz
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
