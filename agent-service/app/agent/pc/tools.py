"""PC 配置推荐的工具集（Java `/internal/v1/pc/**` 的受治理封装）。

节点通过注册表取得治理后的工具再调用，超时、重试、权限与输出截断全部沿用
现有 ToolSpec 机制；节点里不得直接使用 httpx。
"""

from typing import Any

import structlog

from app.agent.pc.status import (
    FAILURE_BUDGET_EXCEEDED,
    FAILURE_CANDIDATE_NOT_IN_POOL,
    FAILURE_COMPATIBILITY_CONFLICT,
    FAILURE_OFFER_UNAVAILABLE,
    FAILURE_USER_TOKEN_MISSING,
)
from app.agent.registry import ToolExecutionError, register_tool
from app.agent.tool_context import get_current_tool_turn
from app.core.config import get_settings
from app.rag import Citation, NoopRetriever, RetrievalRequest, get_retriever
from app.services.control_plane import (
    PC_BUDGET_EXCEEDED,
    PC_BUILD_INCOMPATIBLE,
    PC_BUILD_INCOMPLETE,
    PC_OFFER_UNAVAILABLE,
    PC_USER_TOKEN_INVALID,
    ControlPlaneError,
)
from app.services.pc_client import get_pc_client

logger = structlog.get_logger(__name__)

# 查询类工具一轮最多覆盖 8 个类别，留出重试余量
MAX_CATEGORY_CALLS_PER_TURN = 12
# Architect 首次组装 + 两次修正各一次，配额留出余量
MAX_COMPOSE_CALLS_PER_TURN = 3
# 增量校验只检查已选核心组件，单轮配额由节点按 AGENT__ARCHITECT_MAX_PARTIAL_CHECKS 再收一层
MAX_PARTIAL_CHECKS_PER_TURN = 4
# 组装不遍历组合，但会落快照；超时仍按 30 秒兜底
COMPOSE_TIMEOUT_SECONDS = 30
PARTIAL_CHECK_TIMEOUT_SECONDS = 30

# 知识检索：只读、单轮配额与 Architect 的次数上限是两道独立闸门
KNOWLEDGE_TIMEOUT_SECONDS = 10
KNOWLEDGE_MAX_OUTPUT_TOKENS = 4000
MAX_KNOWLEDGE_CALLS_PER_TURN = 4
MIN_KNOWLEDGE_TOP_K = 1
MAX_KNOWLEDGE_TOP_K = 6
DEFAULT_KNOWLEDGE_TOP_K = 4
MAX_KNOWLEDGE_QUERY_CHARS = 200
# 单条片段进入模型上下文的上限：4 条 × 400 字符，远低于工具输出预算
MAX_KNOWLEDGE_SNIPPET_CHARS = 400
KNOWLEDGE_UNAVAILABLE_MESSAGE = "知识检索暂时不可用，请基于候选与校验结果继续"
KNOWLEDGE_IDENTITY_MISSING_MESSAGE = "缺少用户身份，无法检索知识"

# PC 业务错误 → (失败类型, 是否允许模型修正)
_COMPOSE_FAILURES: dict[str, tuple[str, bool]] = {
    PC_USER_TOKEN_INVALID: (FAILURE_USER_TOKEN_MISSING, False),
    PC_BUILD_INCOMPLETE: (FAILURE_CANDIDATE_NOT_IN_POOL, True),
    PC_OFFER_UNAVAILABLE: (FAILURE_OFFER_UNAVAILABLE, True),
    PC_BUILD_INCOMPATIBLE: (FAILURE_COMPATIBILITY_CONFLICT, True),
    PC_BUDGET_EXCEEDED: (FAILURE_BUDGET_EXCEEDED, True),
}


async def _call_client(operation: Any) -> dict[str, object]:
    """统一收敛上游异常：不把内部地址或堆栈透给用户。"""
    try:
        return await operation
    except ControlPlaneError as exc:
        # 对外仍是统一安全文案；日志保留可判定的上游错误码，便于定位 400/429/5xx
        logger.warning(
            "pc.upstream_error",
            code=exc.code,
            status_code=exc.status_code,
            error_message=exc.message,
        )
        raise ToolExecutionError("配置数据暂时不可用，请稍后重试") from exc


@register_tool(
    name="search_hardware_candidates",
    description="按硬件类别查询可用于装机的候选硬件；不传类别时返回全部类别。",
    timeout_seconds=10,
    max_output_tokens=4000,
    max_calls_per_turn=MAX_CATEGORY_CALLS_PER_TURN,
)
async def search_hardware_candidates(category: str | None = None) -> dict[str, object]:
    """查询候选硬件，金额与规格均为 Java 权威数据。"""
    return await _call_client(get_pc_client().list_candidates(category=category))


@register_tool(
    name="get_benchmark_data",
    description="查询 CPU/GPU 等硬件的跑分数据，用于解释配置性能。",
    timeout_seconds=10,
    max_output_tokens=4000,
    max_calls_per_turn=MAX_CATEGORY_CALLS_PER_TURN,
)
async def get_benchmark_data(
    hardware_id: str | None = None, category: str | None = None
) -> dict[str, object]:
    """查询跑分；优先按硬件，其次按类别。"""
    return await _call_client(
        get_pc_client().list_benchmarks(hardware_id=hardware_id, category=category)
    )


@register_tool(
    name="get_verified_offers",
    description="查询硬件报价及来源统计；可只看人工核验价，演示价必须如实标注。",
    timeout_seconds=10,
    max_output_tokens=6000,
    max_calls_per_turn=MAX_CATEGORY_CALLS_PER_TURN,
)
async def get_verified_offers(
    hardware_id: str | None = None,
    category: str | None = None,
    verified_only: bool = False,
) -> dict[str, object]:
    """查询报价；`verified_only=False` 时结果可能包含演示价。"""
    return await _call_client(
        get_pc_client().list_offers(
            hardware_id=hardware_id,
            category=category,
            verified_only=verified_only,
        )
    )


@register_tool(
    name="compose_pc_build",
    description=(
        "按指定的八类硬件生成并保存一套配置方案；只能使用候选清单中的硬件 ID。"
        "失败时返回结构化失败类型，供选型修正使用。"
    ),
    timeout_seconds=COMPOSE_TIMEOUT_SECONDS,
    max_output_tokens=8000,
    max_calls_per_turn=MAX_COMPOSE_CALLS_PER_TURN,
    is_read_only=False,
)
async def compose_pc_build(
    cpu: str,
    motherboard: str,
    memory: str,
    gpu: str,
    psu: str,
    case: str,
    cooler: str,
    storage: str,
    budget_max_fen: int | None = None,
    workload_profile: str | None = None,
) -> dict[str, object]:
    """组装指定配置；业务失败不抛错，返回 `composed=false` 与失败原因。

    Java 侧的 40307/40308/40309 属于可修正的业务失败，必须保留失败类型；
    缺少用户令牌与其余上游异常不进入修正，直接按失败处理。
    """
    turn = get_current_tool_turn()
    user_token = turn.user_token if turn is not None else None
    if not user_token:
        return _compose_failure(
            FAILURE_USER_TOKEN_MISSING,
            "缺少用户身份，无法生成配置，请重新登录后再试",
            retryable=False,
        )

    request: dict[str, object] = {
        "components": {
            "cpu": cpu,
            "motherboard": motherboard,
            "memory": memory,
            "gpu": gpu,
            "psu": psu,
            "case": case,
            "cooler": cooler,
            "storage": storage,
        },
        "budgetMaxFen": budget_max_fen,
        "workloadProfile": workload_profile,
    }
    try:
        build = await get_pc_client().compose(request, user_token=user_token)
    except ControlPlaneError as exc:
        mapped = _COMPOSE_FAILURES.get(exc.code)
        if mapped is None:
            # 上游不可用或未知错误：交给节点按工具异常处理，不伪造业务失败原因
            logger.warning(
                "pc.compose_upstream_error",
                code=exc.code,
                status_code=exc.status_code,
            )
            raise ToolExecutionError("配置数据暂时不可用，请稍后重试") from exc
        reason, is_retryable = mapped
        return _compose_failure(reason, exc.message, retryable=is_retryable)
    return {"composed": True, "build": build}


def _compose_failure(reason: str, message: str, *, retryable: bool) -> dict[str, object]:
    """统一的业务失败载荷；`retryable` 决定节点是否进入修正。"""
    return {
        "composed": False,
        "failure": {"reason": reason, "message": message, "retryable": retryable},
    }


@register_tool(
    name="check_partial_compatibility",
    description=(
        "校验部分已选组件的兼容性，可在提交整机前发现冲突；"
        "只跑依赖类别都已选的规则，UNKNOWN 表示尚未验证，不能当作通过。"
    ),
    timeout_seconds=PARTIAL_CHECK_TIMEOUT_SECONDS,
    max_output_tokens=4000,
    max_calls_per_turn=MAX_PARTIAL_CHECKS_PER_TURN,
)
async def check_partial_compatibility(
    cpu: str | None = None,
    motherboard: str | None = None,
    memory: str | None = None,
    gpu: str | None = None,
    psu: str | None = None,
    case: str | None = None,
    cooler: str | None = None,
    storage: str | None = None,
) -> dict[str, object]:
    """任意子集校验；至少传入一项，空集合不能伪装成「通过」。"""
    components = {
        category: hardware_id
        for category, hardware_id in (
            ("cpu", cpu),
            ("motherboard", motherboard),
            ("memory", memory),
            ("gpu", gpu),
            ("psu", psu),
            ("case", case),
            ("cooler", cooler),
            ("storage", storage),
        )
        if hardware_id
    }
    if not components:
        raise ToolExecutionError("增量校验至少需要一个已选组件")
    return await _call_client(get_pc_client().validate_partial(components))


@register_tool(
    name="search_knowledge",
    description=(
        "检索装机方法学与权衡原则，只能用于解释「为什么这样取舍」；"
        "型号、规格、价格与兼容性结论必须来自候选清单与服务端校验，不得使用本工具推断。"
    ),
    timeout_seconds=KNOWLEDGE_TIMEOUT_SECONDS,
    max_output_tokens=KNOWLEDGE_MAX_OUTPUT_TOKENS,
    max_calls_per_turn=MAX_KNOWLEDGE_CALLS_PER_TURN,
)
async def search_knowledge(
    query: str, top_k: int = DEFAULT_KNOWLEDGE_TOP_K
) -> dict[str, object]:
    """按当前用户与角色检索知识卡片；失败只降级为「无引用」，不阻塞回合。

    RAG 未启用时返回 `enabled=false` 与空引用；任何情况下都不补写内容。
    """
    normalized = _normalize_knowledge_query(query)
    limit = _clamp_knowledge_top_k(top_k)
    settings = get_settings()
    if not settings.rag.enabled:
        return _knowledge_payload(False, [], False)

    turn = get_current_tool_turn()
    user_id = turn.user_id if turn is not None else ""
    if not user_id:
        # 没有身份就无法执行权限过滤；宁可返回错误也不做匿名检索
        return _knowledge_payload(True, [], False, error=KNOWLEDGE_IDENTITY_MISSING_MESSAGE)

    roles = turn.roles if turn is not None else ()
    try:
        retriever = get_retriever()
        if isinstance(retriever, NoopRetriever):
            return _knowledge_payload(False, [], False)
        # 多取一条用于判断是否被 top_k 截断，随后立即裁掉
        citations = await retriever.retrieve(
            RetrievalRequest(
                query=normalized,
                user_id=user_id,
                roles=roles,
                limit=limit + 1,
            )
        )
    except Exception as exc:
        # 模型或向量库故障：给出明确提示，由节点继续走候选与校验主线
        logger.warning("rag.knowledge_tool_failed", error_type=type(exc).__name__)
        return _knowledge_payload(True, [], False, error=KNOWLEDGE_UNAVAILABLE_MESSAGE)

    return _knowledge_payload(
        True,
        [_knowledge_citation_payload(item) for item in citations[:limit]],
        len(citations) > limit,
    )


def _normalize_knowledge_query(query: str) -> str:
    """空问题与超长问题在工具边界拒绝，避免把无意义查询打到向量库。"""
    normalized = query.strip()
    if not normalized:
        raise ToolExecutionError("知识检索需要非空问题")
    if len(normalized) > MAX_KNOWLEDGE_QUERY_CHARS:
        raise ToolExecutionError(
            f"知识检索问题不能超过 {MAX_KNOWLEDGE_QUERY_CHARS} 字"
        )
    return normalized


def _clamp_knowledge_top_k(top_k: object) -> int:
    """越界按边界收口：模型给 9 时取 6，给 0 时取 1；非法类型退回默认值。"""
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        return DEFAULT_KNOWLEDGE_TOP_K
    return max(MIN_KNOWLEDGE_TOP_K, min(MAX_KNOWLEDGE_TOP_K, top_k))


def _knowledge_citation_payload(citation: Citation) -> dict[str, object]:
    """模型可见引用：保留来源与置信等级，片段裁短以免挤占上下文。"""
    snippet = " ".join(citation.snippet.split())[:MAX_KNOWLEDGE_SNIPPET_CHARS]
    return {
        "source_id": citation.source_id,
        "title": citation.title,
        "snippet": snippet or citation.snippet,
        "score": citation.score,
        "source_name": citation.source_name,
        "confidence_level": citation.confidence_level,
    }


def _knowledge_payload(
    enabled: bool,
    citations: list[dict[str, object]],
    truncated: bool,
    *,
    error: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": enabled,
        "citations": citations,
        "truncated": truncated,
    }
    if error is not None:
        payload["error"] = error
    return payload
