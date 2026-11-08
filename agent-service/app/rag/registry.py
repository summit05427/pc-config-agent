"""检索器注册表：按配置导入接入方模块，关闭时零开销。

约定：`RAG__RETRIEVER_MODULE` 指向的模块必须暴露 `create_retriever()`，
返回实现了 `retrieve(request)` 的对象。导入或工厂异常都在启动期暴露。
"""

import importlib

import structlog

from app.core.config import get_settings
from app.rag.base import NoopRetriever, RagConfigError, Retriever

logger = structlog.get_logger(__name__)

FACTORY_NAME = "create_retriever"

_retriever: Retriever | None = None


def discover_retriever() -> Retriever:
    """导入并构造接入方检索器；配置缺失或实现非法都抛 `RagConfigError`。"""
    module_name = get_settings().rag.retriever_module.strip()
    if not module_name:
        raise RagConfigError(
            "RAG__ENABLED=true 时必须配置 RAG__RETRIEVER_MODULE（点分模块路径）"
        )
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise RagConfigError(
            f"RAG 检索器模块 {module_name} 导入失败（{type(exc).__name__}）：{exc}"
        ) from exc

    factory = getattr(module, FACTORY_NAME, None)
    if not callable(factory):
        raise RagConfigError(
            f"RAG 检索器模块 {module_name} 必须暴露 {FACTORY_NAME}() 工厂函数"
        )

    retriever = factory()
    if not hasattr(retriever, "retrieve"):
        raise RagConfigError(
            f"{module_name}.{FACTORY_NAME}() 的返回值必须实现 retrieve(request)"
        )
    logger.info("rag.retriever_loaded", module=module_name)
    return retriever


def ensure_retriever_loaded() -> Retriever:
    """启动期调用一次；关闭时直接落到 `NoopRetriever`。"""
    global _retriever
    if _retriever is not None:
        return _retriever
    if get_settings().rag.enabled:
        _retriever = discover_retriever()
    else:
        _retriever = NoopRetriever()
    return _retriever


def get_retriever() -> Retriever:
    return ensure_retriever_loaded()


def reset_retriever() -> None:
    """清空缓存；仅供测试隔离使用，生产环境不调用。"""
    global _retriever
    _retriever = None
