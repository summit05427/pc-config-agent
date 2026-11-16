"""应用入口：创建 FastAPI 实例、初始化日志并挂载路由。

为什么用工厂函数 create_app()：
1. 测试时可以按需构造多个应用实例，互不干扰；
2. 中间件、异常处理器、生命周期钩子集中在一处组装；
3. uvicorn 仍可通过 `app.main:app` 定位到实例，启动方式不变。
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.checkpointer import (
    checkpointer_lifespan,
    delete_thread_checkpoint,
    get_connection_pool,
)
from app.agent.hooks import HookModuleImportError, ensure_hooks_loaded
from app.agent.mcp import start_mcp_tools, stop_mcp_tools
from app.agent.profiles import ProfileConfigError, get_profile_store
from app.agent.prompts import PromptNotFoundError, load_openui_prompt, load_system_prompt
from app.agent.registry import (
    ToolModuleImportError,
    ToolRegistrationError,
    ensure_tools_loaded,
)
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware
from app.core.middleware import REQUEST_ID_HEADER, RequestIDMiddleware
from app.core.redis import redis_lifespan
from app.rag import RagConfigError, close_retriever, ensure_retriever_loaded
from app.services.control_plane import close_control_plane_client
from app.services.model_usage import start_usage_reporter, stop_usage_reporter
from app.services.pc_client import close_pc_client
from app.services.session_deletion import (
    detach_session_deletion,
    setup_session_deletion,
    start_session_deletion_worker,
    stop_session_deletion_worker,
)
from app.services.session_store import setup_session_store, unbind_session_store
from app.services.usage_outbox import detach_usage_outbox, setup_usage_outbox

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """集中编排各基础设施的启动与关闭。

    组合逻辑放在应用装配层而不是 core：core 不能反向依赖 agent，
    AsyncExitStack 保证任一必需依赖启动失败时，已建立的资源会被依次释放。
    """
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(checkpointer_lifespan(app))
        # 会话目录与消息转写共用一个池、一个 store；列表不再依赖 Redis 索引
        await setup_session_store(
            get_connection_pool(),
            auto_setup=get_settings().storage.auto_setup,
        )
        # 用量 outbox 同样复用该连接池；建表失败会降级为内存队列，不阻止启动
        await setup_usage_outbox(
            get_connection_pool(),
            auto_setup=get_settings().storage.auto_setup,
        )
        # 会话删除墓碑：检查点删除由后台重试，删除函数从装配层注入，services 不依赖 agent
        await setup_session_deletion(
            get_connection_pool(),
            auto_setup=get_settings().storage.auto_setup,
            delete_checkpoint=delete_thread_checkpoint,
        )
        await stack.enter_async_context(redis_lifespan(app))
        # 使用明细上报是旁路能力：启动消费者后，图节点只做一次 outbox 写入
        await start_usage_reporter()
        # 删除墓碑重试同样是旁路任务：失败只影响检查点清理进度，不影响对话
        await start_session_deletion_worker()
        # MCP 默认关闭；开启后单个 Server 失败只降级，不阻断启动
        await start_mcp_tools()
        try:
            yield
        finally:
            # MCP 连接在关闭 store 前释放，避免工具调用仍持有会话连接
            await stop_mcp_tools()
            # 先停后台任务，再解除存储引用，避免任务在池关闭后仍去查询
            await stop_session_deletion_worker()
            unbind_session_store()
            # 先尽力发完队列（仍可访问连接池），再解除 outbox 与释放控制面连接池
            await stop_usage_reporter()
            detach_usage_outbox()
            detach_session_deletion()
            # 先关闭 PC 查询连接，再释放控制面令牌连接池
            await close_pc_client()
            await close_control_plane_client()
            # 检索器可能持有独立的向量库连接池，最后释放
            await close_retriever()


def create_app() -> FastAPI:
    """组装并返回 FastAPI 应用。"""
    settings = get_settings()
    configure_logging(settings)

    # 生产不暴露 OpenAPI 与交互文档：它们会把全部路由、Schema 与错误码结构暴露给任何
    # 能访问 /agent/ 的调用方；与 Java 侧 springdoc 在 prod 关闭的策略保持一致。
    is_prod = settings.app_env == "prod"

    # 提示词属于启动依赖：缺失/为空时直接失败，避免第一个请求才暴露。
    # OpenUI 契约只在开关开启时读取，关闭时不产生任何额外文件依赖。
    try:
        load_system_prompt()
        if settings.openui.enabled:
            load_openui_prompt()
    except PromptNotFoundError as exc:
        raise RuntimeError(f"提示词加载失败：{exc}") from exc

    # 工具在启动期完成发现与校验：模块导入失败或工具重名直接拒绝启动，
    # 避免服务起来后第一个请求才发现工具不可用
    try:
        ensure_tools_loaded()
    except (ToolModuleImportError, ToolRegistrationError) as exc:
        raise RuntimeError(f"工具注册失败：{exc}") from exc

    # 钩子模块同样在启动期导入：配置了却导入失败属于部署错误，直接拒绝启动
    try:
        ensure_hooks_loaded()
    except HookModuleImportError as exc:
        raise RuntimeError(f"钩子加载失败：{exc}") from exc

    # RAG 关闭时不导入任何检索器；开启后模块缺失或实现非法都拒绝启动
    if settings.rag.enabled:
        try:
            ensure_retriever_loaded()
        except RagConfigError as exc:
            raise RuntimeError(f"RAG 检索器加载失败：{exc}") from exc

    # Profile 也必须在启动期加载：id 重复、提示词缺失、工具未注册都应拒绝启动
    try:
        get_profile_store()
    except ProfileConfigError as exc:
        raise RuntimeError(f"Agent Profile 加载失败：{exc}") from exc

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        # 启动时建立会话存储与 Redis，退出时按相反顺序释放连接池
        lifespan=app_lifespan,
        # 生产关闭 /docs、/redoc 与 /openapi.json；dev/staging 保留以便联调
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # 中间件按"后添加先执行"的顺序包裹：CORS 在最外层，先处理预检请求
    if settings.metrics.enabled:
        # 指标中间件放在 RequestID 内层，确保访问日志先绑定 request_id
        app.add_middleware(
            MetricsMiddleware,
            metrics_path=f"{settings.api_prefix.rstrip('/')}/metrics",
        )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # 前端需要读到请求 ID 才能和后端日志关联
        expose_headers=[REQUEST_ID_HEADER],
    )

    register_exception_handlers(app)

    # 所有业务路由统一挂在 API_PREFIX 下（默认 /api/v1），便于版本演进
    app.include_router(api_router, prefix=settings.api_prefix)

    logger.info("app.created", app_env=settings.app_env, api_prefix=settings.api_prefix)
    return app


# 模块级实例：uvicorn 通过 "app.main:app" 定位它
app = create_app()
