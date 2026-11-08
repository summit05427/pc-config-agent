# syntax=docker/dockerfile:1
# =============================================================
# agent-service 单服务镜像
# 只负责构建本服务；三端串联的全局 docker-compose.yml 由项目根目录维护
# 构建：docker build -t agent-service:dev .
# =============================================================

# ---------- 阶段 1：依赖安装（builder） ----------
FROM python:3.12-slim AS builder

# uv：按 uv.lock 精确还原依赖，保证镜像依赖与本地开发完全一致
RUN pip install --no-cache-dir uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 先只拷贝依赖清单：只要依赖没变，这一层就能命中缓存，
# 改业务代码不会触发重新下载依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---------- 阶段 2：运行时（runtime） ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# 非 root 运行：容器被攻破时攻击者拿不到 root 权限
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# 只带虚拟环境与源码；测试、文档、缓存一律不进镜像
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# 不依赖 curl：用标准库探活，避免为一次健康检查多装一个包
# start-period 给启动留时间，避免容器刚起就被判定为不健康
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"

# 容器内是 Linux，不存在 Windows 的 ProactorEventLoop 问题，直接跑 uvicorn，
# 不需要 run.py（run.py 只服务于 Windows 本地开发）
# --proxy-headers / --forwarded-allow-ips：让日志能取到 Nginx 转发的真实客户端 IP。
# 该参数仅在「容器只通过内网由 Nginx 访问」时安全，切勿直接暴露到公网
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
