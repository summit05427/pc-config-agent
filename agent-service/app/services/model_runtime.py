"""模型运行时门面：一次调用把 Profile、请求模型与用户令牌装配成可运行的 Agent。

为什么需要这层门面：
1. 「解析运行时 → 兑换凭证 → 选默认图/按运行时构图」是固定顺序，散落在路由里时，
   任何一处新增分支都可能把顺序改错（例如先构图再兑换，就永远拿不到 BYOK 密钥）；
2. 凭证撤销后必须同时清掉图缓存与模型实例缓存，这对调用方是无关细节，
   由门面统一处理可以避免某个调用方只清一半；
3. 路由只关心传输（SSE 编码、锁、幂等），装配细节留在服务层，便于直接单测。
"""

from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import SecretStr

from app.agent.graph import build_agent, get_agent, get_agent_for_runtime, invalidate_credential
from app.agent.profiles import AgentProfile
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services import control_plane
from app.services.model_resolver import (
    ResolvedRuntime,
    resolve_credential,
    resolve_runtime,
)

# 凭证已撤销/不可用：必须清掉本地缓存的实例，避免残留密钥被继续使用
_CREDENTIAL_INVALIDATING_CODES = frozenset({"credential_revoked"})

# 目录能力位：请求侧门控只认这个名字，禁止按 Provider 猜能力
REASONING_CAPABILITY = "reasoning"


@dataclass(frozen=True)
class PreparedAgent:
    """流开始前装配好的图与运行时；`runtime` 为空表示沿用进程默认模型。"""

    graph: CompiledStateGraph
    runtime: ResolvedRuntime | None = None
    # 用户令牌只用于本回合调用 Java 内部接口，禁止写入图状态
    user_token: SecretStr | None = None


def _default_graph(
    profile: AgentProfile, checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    """未使用运行时模型时的图选择。

    默认 Profile 沿用进程级默认图；其他 Profile 按 `agent_id` 独立缓存，
    避免不同人格的提示词与温度互相串扰。传入 checkpointer 时按离屏调用处理，
    只构建一次性图，不污染进程缓存。
    """
    if checkpointer is not None:
        return build_agent(profile=profile, checkpointer=checkpointer)
    if profile.id == get_settings().agent.default_profile:
        return get_agent()
    return get_agent_for_runtime(None, agent_id=profile.id)


def _ensure_reasoning_supported(runtime: ResolvedRuntime, reasoning: bool | None) -> None:
    """请求要求开启思考时，必须由目录能力位放行。

    网关开启了 `drop_params`，不支持的参数会被静默丢弃：如果只依赖网关，
    前端会看到「已开启思考」但实际没有任何思考内容，无法归因。因此门控必须在
    Agent 侧显式拒绝，且早于 BYOK 凭证兑换，避免白耗一次一次性凭证。
    """
    if reasoning is not True or REASONING_CAPABILITY in runtime.capabilities:
        return
    raise AppError(
        "当前模型不支持开启思考",
        code=control_plane.CAPABILITY_UNSUPPORTED,
        status_code=422,
    )


async def prepare_agent(
    profile: AgentProfile,
    *,
    user_id: str,
    thread_id: str,
    access_token: SecretStr | None,
    requested_model: str | None,
    client_idempotency_key: str | None = None,
    reasoning: bool | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> PreparedAgent:
    """按原顺序完成「解析 → 门控 → 兑换 → 构图」，返回可直接运行的图。

    调用方不需要知道四步顺序，也不需要知道撤销时清哪两个缓存：关闭运行时或解析
    失败时自动回落到默认图，凭证撤销时由本函数清理缓存后继续抛出原异常。

    :param reasoning: 本轮是否要求模型思考；`None` 表示沿用模型默认行为。
        运行时关闭时没有目录可依据，该参数被忽略。
    :param checkpointer: 仅离屏调用（如真实评测）传入；生产留空，沿用进程缓存与
        生产检查点，避免评测会话写入业务库。
    :raises AppError: 开启运行时但缺少访问令牌（401）、模型不支持所需能力（422），
        或解析/兑换阶段的业务错误。
    """
    settings = get_settings()
    if not settings.model_runtime.enabled:
        # 关闭时保持原有单模型逻辑，不发起任何出站请求
        return PreparedAgent(
            graph=_default_graph(profile, checkpointer),
            runtime=None,
            user_token=access_token,
        )

    if access_token is None:
        raise AppError("缺少访问令牌", code="unauthorized", status_code=401)

    runtime = await resolve_runtime(
        user_id=user_id,
        thread_id=thread_id,
        user_token=access_token.get_secret_value(),
        requested_model=requested_model,
        default_model=profile.model.default_key,
        client_idempotency_key=client_idempotency_key,
    )
    if runtime is None:
        # 控制面不可达且未显式指定模型：显式降级到进程默认模型
        return PreparedAgent(
            graph=_default_graph(profile, checkpointer),
            runtime=None,
            user_token=access_token,
        )

    _ensure_reasoning_supported(runtime, reasoning)

    try:
        credential = await resolve_credential(runtime)
    except AppError as error:
        if error.code in _CREDENTIAL_INVALIDATING_CODES and runtime.credential_id:
            # 凭证已撤销：丢弃本地图与模型实例，下一次请求必须重新走 lease
            invalidate_credential(runtime.credential_id)
        raise

    graph = get_agent_for_runtime(
        runtime,
        agent_id=profile.id,
        api_key=credential.api_key if credential is not None else None,
        base_url=credential.base_url if credential is not None else None,
        checkpointer=checkpointer,
    )
    return PreparedAgent(graph=graph, runtime=runtime, user_token=access_token)
