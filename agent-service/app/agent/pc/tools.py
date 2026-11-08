"""PC 配置推荐的工具集（Java `/internal/v1/pc/**` 的受治理封装）。

节点通过注册表取得治理后的工具再调用，超时、重试、权限与输出截断全部沿用
现有 ToolSpec 机制；节点里不得直接使用 httpx。
"""

from typing import Any

from app.agent.registry import ToolExecutionError, register_tool
from app.agent.tool_context import get_current_tool_turn
from app.services.control_plane import ControlPlaneError
from app.services.pc_client import get_pc_client

# 查询类工具一轮最多覆盖 8 个类别，留出重试余量
MAX_CATEGORY_CALLS_PER_TURN = 12
# 求解在兼容性失败后允许自动重解一次，配额留出余量
MAX_SOLVE_CALLS_PER_TURN = 3


def _require_user_token() -> str:
    """求解与快照读取属于用户维度；缺失身份时给安全错误而不是匿名代查。"""
    turn = get_current_tool_turn()
    token = turn.user_token if turn is not None else None
    if not token:
        raise ToolExecutionError("缺少用户身份，无法生成配置，请重新登录后再试")
    return token


async def _call_client(operation: Any) -> dict[str, object]:
    """统一收敛上游异常：不把内部地址或堆栈透给用户。"""
    try:
        return await operation
    except ControlPlaneError as exc:
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
    name="solve_pc_build",
    description="按预算与场景求解一套完整的八类硬件配置；无解时返回结构化失败原因。",
    timeout_seconds=25,
    max_output_tokens=8000,
    max_calls_per_turn=MAX_SOLVE_CALLS_PER_TURN,
    is_read_only=False,
)
async def solve_pc_build(
    budget_max_fen: int | None = None,
    scenario: str = "BALANCED",
    min_memory_gb: int | None = None,
    min_storage_gb: int | None = None,
    require_verified_offers: bool = False,
) -> dict[str, object]:
    """求解配置；预算单位为整数分。"""
    request: dict[str, object] = {
        "budgetMaxFen": budget_max_fen,
        "scenario": scenario,
        "minMemoryGb": min_memory_gb,
        "minStorageGb": min_storage_gb,
        "requireVerifiedOffers": require_verified_offers,
    }
    return await _call_client(
        get_pc_client().solve(request, user_token=_require_user_token())
    )


@register_tool(
    name="validate_pc_build",
    description="校验八类硬件组合的兼容性；UNKNOWN 表示尚未验证，不能当作通过。",
    timeout_seconds=10,
    max_output_tokens=4000,
    max_calls_per_turn=MAX_SOLVE_CALLS_PER_TURN,
)
async def validate_pc_build(
    cpu: str,
    motherboard: str,
    memory: str,
    gpu: str,
    psu: str,
    case: str,
    cooler: str,
    storage: str,
) -> dict[str, object]:
    """按类别校验配置；八个标识缺一不可。"""
    hardware_ids = {
        "cpu": cpu,
        "motherboard": motherboard,
        "memory": memory,
        "gpu": gpu,
        "psu": psu,
        "case": case,
        "cooler": cooler,
        "storage": storage,
    }
    return await _call_client(get_pc_client().validate(hardware_ids))
