"""应用配置中心。

设计目标：
1. 单一来源：所有环境变量只在这里声明与校验，业务代码通过 settings 读取，禁止散落 os.getenv。
2. 启动即校验：类型错误、缺失必填项在进程启动时暴露，而不是运行到某个接口才报错。
3. 敏感信息保护：密钥统一用 SecretStr 包装，打印或写日志时自动脱敏。
4. 多环境切换：.env 只服务于本地开发，生产环境使用真实环境变量覆盖（优先级更高）。
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# app/core/config.py -> parents[2] 即项目根目录，避免启动目录不同导致读不到 .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 生产环境守卫：这些片段出现在配置里说明仍在用示例值，必须拒绝启动
PLACEHOLDER_SECRET_MARKERS = ("replace-with", "change-me", "your-secret")
PLACEHOLDER_API_KEY_PREFIXES = ("sk-replace",)

# 验收夹具只返回固定假数据；生产环境误启用会让线上静默绕过真实实现
ACCEPTANCE_MODULE_PREFIX = "acceptance."

# 容器/密钥管理里常把 PEM 压成单行，换行写成字面量 \n；读取后必须还原
PEM_NEWLINE_ESCAPE = "\\n"


def _normalize_pem_text(value: str) -> str:
    """把单行 PEM 中的字面量 \\n 还原为真实换行，否则 cryptography 无法解析。"""
    return value.replace(PEM_NEWLINE_ESCAPE, "\n").strip()


# 默认模型使用业务标识 provider:model，与网关 model_list 中的 model_name 一致
DEFAULT_MODEL = "deepseek:deepseek-flash"


class LLMSettings(BaseModel):
    """大模型配置，对应环境变量前缀 LLM__（如 LLM__MODEL）。

    存在两种互斥模式，由是否配置 `gateway_api_key` 决定：
    - 网关模式：请求经 LiteLLM 出站，Provider 协议、重试、故障切换都由网关承担；
    - 直连模式：仅用于 Solo 等没有网关的部署，只支持 OpenAI 兼容端点。
    """

    model: str = DEFAULT_MODEL
    # 网关地址：容器内走服务名，宿主机调试改为 http://127.0.0.1:4000
    gateway_base_url: str = "http://litellm:4000"
    # 网关鉴权密钥（即 LiteLLM master key）；配置后进入网关模式
    gateway_api_key: SecretStr | None = None
    # 直连模式（Solo）使用的 Provider 密钥与地址
    api_key: SecretStr | None = None
    base_url: str | None = "https://api.deepseek.com/v1"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=60.0, gt=0)


class AuthSettings(BaseModel):
    """鉴权配置，对应环境变量前缀 AUTH__（如 AUTH__JWT_PUBLIC_KEY）。

    Agent 只持公钥验签：签名私钥归 Java 所有，落在本服务等于把签发权交了出去。
    """

    # PKIX PEM 公钥文本，对应 Java 的 JWT_PUBLIC_KEY
    jwt_public_key: str
    # 收窄为仅 RS256：算法写死可杜绝 HS* 混淆与 alg=none 之类的降级攻击
    jwt_algorithm: Literal["RS256"] = "RS256"
    # 只接受指定签发方签发的令牌，避免其他系统签发的 Token 混入
    issuer: str = Field(default="agent-application-service", min_length=1)
    # 必填且强制校验：多系统共用 iss 时，aud 是区分目标受众的最后一道闸
    audience: str = Field(default="agent-clients", min_length=1)
    # Java 主密钥的 kid；未配置时按默认 kid 注册主公钥
    jwt_kid: str | None = None
    # 仅 /auth/dev-token 本地自签使用；生产环境禁止注入任何私钥
    dev_private_key: SecretStr | None = None
    dev_kid: str = Field(default="rsa-dev", min_length=1)
    access_token_expire_minutes: int = Field(default=60, gt=0)

    @field_validator("jwt_public_key", mode="before")
    @classmethod
    def normalize_public_key(cls, value: str) -> str:
        """单行 PEM 还原换行；空值直接拒绝，避免启动后所有请求都 401。"""
        if not isinstance(value, str):
            return value
        normalized = _normalize_pem_text(value)
        if not normalized:
            raise ValueError("AUTH__JWT_PUBLIC_KEY 不能为空")
        return normalized

    @field_validator("jwt_public_key")
    @classmethod
    def validate_public_key_pem(cls, value: str) -> str:
        """启动即校验 PEM 可解析。

        否则服务能正常起来，但每次验签都失败并返回 401，现象是「所有人都登不上」，
        与「配置错误应在启动时暴露」的设计目标相悖，排查成本也远高于直接启动失败。
        """
        try:
            load_pem_public_key(value.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError("AUTH__JWT_PUBLIC_KEY 不是合法的 PEM 公钥") from exc
        return value

    @field_validator("dev_private_key", mode="before")
    @classmethod
    def normalize_dev_private_key(cls, value: object) -> object:
        """空字符串等同于未配置；单行 PEM 同样还原换行。"""
        if isinstance(value, str):
            return _normalize_pem_text(value) or None
        return value

    @field_validator("jwt_kid")
    @classmethod
    def normalize_jwt_kid(cls, value: str | None) -> str | None:
        """空字符串等同于未配置，避免注册一个空 kid 的公钥。"""
        if value is None:
            return None
        return value.strip() or None

    @field_validator("audience")
    @classmethod
    def normalize_audience(cls, value: str) -> str:
        """首尾空白会让 aud 匹配恒失败，直接归一化掉。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("AUTH__AUDIENCE 不能为空")
        return normalized


class ModelRuntimeSettings(BaseModel):
    """模型运行时开关，对应环境变量前缀 MODEL_RUNTIME__。

    关闭时保持原有单模型逻辑，不发起任何控制面出站请求。
    """

    enabled: bool = False


class ControlPlaneSettings(BaseModel):
    """Agent → Java 控制面调用配置，对应环境变量前缀 CONTROL_PLANE__。

    服务令牌凭据必须与 Java 的 INTERNAL_AUTH_CLIENT_ID / INTERNAL_AUTH_CLIENT_SECRET 一致；
    secret 只从环境变量注入，禁止写入代码、日志或异常文本。
    """

    # 容器内默认走 Compose 服务名；本地开发在 .env 中覆盖为 127.0.0.1
    base_url: str = Field(default="http://application-service:8080", min_length=1)
    client_id: str = Field(default="agent-service", min_length=1, max_length=64)
    client_secret: SecretStr | None = None
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        """去掉末尾斜杠，避免拼出 // 路径；只允许 http/https。"""
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("CONTROL_PLANE__BASE_URL 必须是 http(s) 地址")
        return normalized

    @field_validator("client_secret", mode="before")
    @classmethod
    def normalize_client_secret(cls, value: object) -> object:
        """空字符串等同于未配置，避免把空值当成合法凭据。"""
        if isinstance(value, str):
            return value.strip() or None
        return value


class StorageSettings(BaseModel):
    """会话持久化配置，对应环境变量前缀 STORAGE__。

    backend=memory 仅用于测试；生产必须是 postgres，否则多副本之间会话不共享。
    """

    backend: Literal["memory", "postgres"] = "memory"
    postgres_url: SecretStr | None = None
    pool_size: int = Field(default=5, ge=1, le=50)
    # 启动时自动建表（幂等）；托管数据库无 DDL 权限时可关闭，改为手工迁移
    auto_setup: bool = True

    @field_validator("postgres_url", mode="before")
    @classmethod
    def normalize_postgres_url(cls, value: object) -> object:
        """空字符串等同于未配置：Solo 模式用 memory 时不需要连接串。"""
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_postgres_url(self) -> "StorageSettings":
        """选了 postgres 却没给连接串，属于配置错误，启动就该失败。"""
        if self.backend == "postgres" and self.postgres_url is None:
            raise ValueError("STORAGE__BACKEND=postgres 时必须提供 STORAGE__POSTGRES_URL")
        return self


class RedisSettings(BaseModel):
    """Redis 基础设施配置，对应环境变量前缀 REDIS__。

    模板只提供通用能力，不预设业务策略：
    - required=false：Redis 不可用时降级启动并记录 warning，适合本地开发；
    - required=true：连接失败直接拒绝启动，生产环境应显式打开。
    """

    url: SecretStr | None = None
    required: bool = False
    # 连接池上限与超时必须显式配置，避免默认值在高并发下耗尽连接
    max_connections: int = Field(default=10, ge=1, le=200)
    socket_timeout_seconds: float = Field(default=2.0, gt=0)
    connect_timeout_seconds: float = Field(default=2.0, gt=0)
    # 空闲连接健康检查间隔，0 表示关闭
    health_check_interval_seconds: int = Field(default=30, ge=0)
    # 所有 key 统一带此前缀，避免与共享 Redis 实例中的其他服务冲突
    key_prefix: str = Field(default="agent", min_length=1, max_length=32)
    # 缓存类 key 的默认过期时间，禁止写入无 TTL 的临时数据
    default_ttl_seconds: int = Field(default=300, gt=0)
    # 分布式锁默认持有时间：必须大于临界区耗时，否则锁会提前释放
    lock_ttl_seconds: int = Field(default=30, gt=0)
    # 幂等记录默认保留时间，调用方可以按接口覆盖
    idempotency_ttl_seconds: int = Field(default=86400, gt=0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: SecretStr | None) -> SecretStr | None:
        """空字符串等同于未配置，避免把空值当成合法连接串。

        Solo 模式通过空值显式关闭 Redis；是否允许缺失由 required 决定。
        """
        if value is not None and not value.get_secret_value().strip():
            return None
        return value

    @field_validator("key_prefix")
    @classmethod
    def validate_key_prefix(cls, value: str) -> str:
        """前缀里出现冒号会破坏 key 的分段结构。"""
        if ":" in value or value != value.strip():
            raise ValueError("REDIS__KEY_PREFIX 不能包含冒号或首尾空格")
        return value

    @model_validator(mode="after")
    def validate_required_url(self) -> "RedisSettings":
        """声明 Redis 为必需却不给连接串，属于配置错误，启动就该失败。"""
        if self.required and self.url is None:
            raise ValueError("REDIS__REQUIRED=true 时必须提供 REDIS__URL")
        return self


def _parse_comma_separated(value: object) -> object:
    """环境变量按逗号分隔；空值等同于未配置。"""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class AgentSettings(BaseModel):
    """Agent 运行时行为配置，对应环境变量前缀 AGENT__。

    这些参数决定一次对话能否稳定收尾，属于稳定性基线，不涉及具体业务。
    """

    # 传给模型的上下文预算（token）；超出后按「完整消息单元」从旧到新裁剪
    context_max_tokens: int = Field(default=6000, gt=0)
    # ReAct 循环上限，防止模型反复调用工具导致无限循环
    recursion_limit: int = Field(default=12, ge=1, le=100)
    # 单次对话流的总超时；超时下发 error 事件并停止图执行
    request_timeout_seconds: float = Field(default=120.0, gt=0)
    # 同一会话的锁持有时间：必须大于最长生成耗时，否则锁会提前释放
    thread_lock_ttl_seconds: int = Field(default=300, gt=0)
    # 抢锁等待窗口，0 表示立即失败（另一个请求正在生成时返回 409）
    thread_lock_wait_seconds: float = Field(default=3.0, ge=0)
    # SSE 心跳间隔：模型长时间无输出时下发注释行，避免代理判定连接空闲
    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)
    # 系统提示词目录中的文件名（不含 .md），用于切换人格与规则
    system_prompt: str = Field(default="pc-config-system", min_length=1, max_length=64)
    # 每回合允许的增量兼容性校验次数（0 表示关闭）；工具自身还有单轮配额兜底。
    # 必须 ≥ 修正次数 + 1（ARCHITECT_MAX_REPAIRS=2），否则最后一次修正拿不到校验反馈，
    # 只能等 compose 用通用原因失败，修正必然空转。
    architect_max_partial_checks: int = Field(default=3, ge=0, le=4)
    # Architect 每回合允许调用知识检索的次数（0 表示关闭）；工具自身还有单轮配额兜底
    architect_max_knowledge_calls: int = Field(default=2, ge=0, le=4)
    # Architect 结构化选型的单独输出预算：推理模型的思考 token 计入输出，
    # 沿用 LLM__MAX_TOKENS=2048 会把 BuildProposal 的 JSON 截断
    architect_max_tokens: int = Field(default=4096, gt=0)
    # 工具默认超时（秒）；单个工具可在注册时覆盖
    tool_timeout_seconds: float = Field(default=10.0, gt=0)
    # 工具失败后的重试次数；0 表示不重试
    tool_max_retries: int = Field(default=1, ge=0, le=5)
    # 追加的工具模块（点分路径，逗号分隔）；内置 tools 与 tools_ext 无需在此声明
    tool_modules: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("tool_modules", mode="before")
    @classmethod
    def parse_tool_modules(cls, value: object) -> object:
        """`NoDecode` 让 pydantic-settings 跳过 JSON 解码，否则逗号分隔的字符串
        会在读取配置时就被判定为非法 JSON。
        """
        return _parse_comma_separated(value)

    # 追加的钩子模块（点分路径，逗号分隔）；未配置时钩子注册表为空
    hooks_modules: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("hooks_modules", mode="before")
    @classmethod
    def parse_hooks_modules(cls, value: object) -> object:
        return _parse_comma_separated(value)

    # 长会话摘要：默认关闭；开启后只有历史超过阈值才会产生额外模型调用
    summary_enabled: bool = Field(default=False)
    summary_trigger_tokens: int = Field(default=5000, ge=1, le=100_000)

    # 已废弃（2026-10-29）：会话列表改为读取 Postgres 的 session_meta，
    # 这两项不再生效；暂时保留只为兼容现有 .env，后续版本删除
    session_index_ttl_seconds: int = Field(default=2592000, gt=0, deprecated=True)
    # 已废弃：同上，保留键名避免旧部署启动失败
    session_index_max: int = Field(default=100, ge=1, le=1000, deprecated=True)

    # Agent Profile 配置目录（相对路径按服务根目录解析）；子目录中的 YAML 也会加载
    profiles_dir: str = Field(default="app/agents", min_length=1)
    # 请求未携带 agent_id 时使用的 Profile
    default_profile: str = Field(default="pc-config", pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    # 工具单次返回的 token 上限；超出后截断并附加提示，避免一次返回挤爆上下文
    tool_max_output_tokens: int = Field(default=2000, gt=0)
    # 同一工具在一轮对话内的调用上限；超限时返回提示文本而不是抛错
    tool_max_calls_per_turn: int = Field(default=3, ge=1, le=20)
    # 工具返回给模型前是否脱敏（手机号、邮箱、身份证、API Key / Bearer 凭据）
    tool_redact_output: bool = True


class OpenUiSettings(BaseModel):
    """生成式 UI 输出配置，对应环境变量前缀 OPENUI__。

    关闭时模型只输出纯文本，行为与接入前完全一致；开启后把前端生成的
    组件契约注入系统提示词，因此必须与前端 `VITE_OPENUI_ENABLED` 同步开启。
    """

    enabled: bool = False
    # 提示词文件名（app/agent/prompts 下，不含 .md），由 frontend 生成脚本产出；
    # 与 AGENT__SYSTEM_PROMPT 共用同一套名称白名单，排除路径分隔符
    prompt_name: str = Field(
        default="openui",
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    # 单次回答的顶层 UI 块上限，写入提示词约束输出规模，避免一次生成过长 UI
    max_blocks: int = Field(default=4, ge=1, le=10)


class MetricsSettings(BaseModel):
    """Prometheus 指标配置。

    安全策略：网关（Nginx）白名单是第一道防线，应用内 token 是兜底。
    `token` 为空时不做应用内校验，完全依赖网关；配置后请求必须携带
    `X-Metrics-Token`，防止网关配置漏项导致指标直接对外。
    """

    enabled: bool = True
    token: SecretStr | None = Field(default=None, min_length=16, max_length=128)


class MCPSettings(BaseModel):
    """MCP 接入配置，对应环境变量前缀 MCP__。

    模板只支持一种拓扑：MCP Server 由 LiteLLM 网关托管，Agent 作为客户端
    连接网关聚合端点。Solo 模式没有网关，因此不提供 MCP；开启但缺少网关
    密钥时只告警跳过，不阻断启动。默认关闭时不会导入 MCP SDK，也不建连。
    """

    enabled: bool = False
    # 覆盖聚合端点；留空则由 llm.gateway_base_url 推导为 {base}/mcp
    gateway_url: str | None = None
    # 只接入列出的工具（网关返回的原始工具名）；为空表示全部接入
    allowed_tools: list[str] = Field(default_factory=list)
    # 建连、初始化与 tools/list 的总时限；失败只降级
    connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # 单次工具调用时限，传给注册表做治理超时
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class RagSettings(BaseModel):
    """可选 RAG 配置，对应环境变量前缀 RAG__。

    开关默认值由 embedding 配置推导：模型与维度都齐备时开启，否则关闭。
    推导放在启动期一次完成，缺少 embedding 配置只表示「未启用」，不会拒绝启动。
    关闭时不导入任何检索器模块，也不发起外部请求。

    内置 pgvector 检索器还会读取 embedding 与融合参数：显式开启后
    `embedding_model` 为空或维度非正时由检索器工厂抛错，而不是用假向量兜底。
    """

    enabled: bool = False
    retriever_module: str = Field(default="", max_length=200)
    top_k: int = Field(default=5, ge=1, le=20)
    # Embedding 与向量维度必须成对配置；维度用于建表与结果校验
    embedding_model: str = Field(default="", max_length=200)
    embedding_dimensions: int = Field(default=0, ge=0, le=8192)
    # 百炼 text-embedding-v4 单次最多 10 条，默认值取所有已知 provider 的下限；
    # 换成支持更大批次的 provider 时可上调，但不能超过其上限
    embedding_batch_size: int = Field(default=10, ge=1, le=256)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    # RRF（Reciprocal Rank Fusion）平滑常数：越大越弱化头部名次差异
    rrf_k: int = Field(default=60, ge=1, le=1000)
    # 每个通道的召回数量 = limit * 倍数；上限在检索器内再收口
    recall_multiplier: int = Field(default=4, ge=1, le=20)

    @model_validator(mode="before")
    @classmethod
    def derive_enabled_from_embedding(cls, values: object) -> object:
        """未显式配置 `RAG__ENABLED` 时，按 embedding 模型与维度是否齐备判定。

        显式 true/false 始终优先；只在缺省时推导，避免把「没配 embedding」
        误判成启动错误——那种情况只意味着 RAG 未启用。
        """
        if not isinstance(values, dict) or values.get("enabled") is not None:
            return values
        model_name = str(values.get("embedding_model") or "").strip()
        try:
            dimensions = int(values.get("embedding_dimensions") or 0)
        except (TypeError, ValueError):
            dimensions = 0
        return {**values, "enabled": bool(model_name) and dimensions > 0}


class HitlSettings(BaseModel):
    """人机协同（HITL）配置，对应环境变量前缀 HITL__。

    中断会把图状态停留在 checkpointer 中等待用户回答，恢复依赖持久化会话。
    默认关闭以保证既有澄清/构建流程零回归；显式开启时必须是 postgres 后端，
    memory 后端跨进程不共享中断，静默降级会让用户拿到无法恢复的对话。
    """

    enabled: bool = False
    # 中断有效期：超过后恢复请求按「中断已过期」拒绝，避免长期悬挂的中断被误恢复
    interrupt_ttl_seconds: int = Field(default=1800, gt=0, le=86400)


class GuardSettings(BaseModel):
    """输入侧护栏，对应环境变量前缀 GUARD__。

    与输出护栏互补：这里拦截进入模型之前的可疑内容。命中即拒绝，
    因此特征只保留高置信度模式；紧急情况下可用 enabled=false 整体关闭。
    """

    enabled: bool = True
    # 与 ChatRequest 的长度上限对齐；调小可进一步收紧，调大不会突破请求模型校验
    max_input_chars: int = Field(default=4000, ge=1, le=20000)
    # 关闭后只保留长度/字符类校验，放行疑似提示词注入的输入（用于灰度对比）
    block_on_injection: bool = True


class RateLimitSettings(BaseModel):
    """对话接口限流，对应环境变量前缀 RATE_LIMIT__。

    按登录用户做 Redis 固定窗口计数：流式对话单轮成本高，限流是成本控制的第一道闸。
    Redis 不可用时默认放行（fail-open），与幂等降级策略一致；生产若要严格限流可置为 false。
    """

    enabled: bool = True
    # 0 表示关闭计数（保留配置位，便于不改代码临时停用）
    chat_per_minute: int = Field(default=20, ge=0, le=600)
    window_seconds: int = Field(default=60, ge=10, le=3600)
    fail_open: bool = True


class EvalSettings(BaseModel):
    """真实评测身份，对应环境变量前缀 EVALS__。

    `--real` 复用生产的模型解析与工具链路，因此必须携带一枚有效的用户访问令牌：
    模型任务与用户维度工具都要用它向 Java 证明「代表哪个用户」。未配置时评测会
    明确报「模型未解析」，而不是退回正则/确定性兜底把问题伪装成成功。
    """

    user_token: SecretStr | None = None
    user_id: str = Field(default="eval-user", min_length=1, max_length=64)
    # 门禁成本口径：按模型目录的每百万 token 单价折算；未配置时成本记为未校验
    price_input_per_million: float | None = Field(default=None, ge=0)
    price_output_per_million: float | None = Field(default=None, ge=0)
    price_currency: str = Field(default="CNY", min_length=1, max_length=8)


class Settings(BaseSettings):
    """全局配置根对象。

    优先级：真实环境变量 > .env > 字段默认值。
    因此同一份代码在本地和容器中无需修改，只需注入不同的环境变量。
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        # 嵌套配置用双下划线分隔：LLM__MODEL -> llm.model
        env_nested_delimiter="__",
        # 允许 .env 里存在暂未使用的变量，避免新增配置时报错
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "agent-service"
    app_env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True
    api_prefix: str = "/api/v1"
    # 复杂类型（list）从环境变量读取时必须是 JSON，默认值用工厂函数避免可变对象共享
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    llm: LLMSettings = Field(default_factory=LLMSettings)
    auth: AuthSettings
    model_runtime: ModelRuntimeSettings = Field(default_factory=ModelRuntimeSettings)
    control_plane: ControlPlaneSettings = Field(default_factory=ControlPlaneSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    openui: OpenUiSettings = Field(default_factory=OpenUiSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    hitl: HitlSettings = Field(default_factory=HitlSettings)
    guard: GuardSettings = Field(default_factory=GuardSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    evals: EvalSettings = Field(default_factory=EvalSettings)

    @model_validator(mode="after")
    def validate_hitl_storage(self) -> "Settings":
        """启用 HITL 时必须是 postgres 后端。

        memory 后端无法跨进程保存中断，继续运行只会让用户拿到无法恢复的对话；
        这里直接拒绝启动，而不是在中断发生时静默降级。
        """
        if self.hitl.enabled and self.storage.backend != "postgres":
            raise ValueError(
                "HITL__ENABLED=true 时 STORAGE__BACKEND 必须为 postgres；"
                "memory 后端不保存中断，无法恢复"
            )
        return self

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """生产环境 fail-fast。

        带病运行比启动失败更危险：调试模式会泄露堆栈、占位密钥等于没有鉴权、
        memory 会话在多副本间不共享、通配符 CORS 会放开所有来源。
        """
        if self.app_env != "prod":
            return self

        problems: list[str] = []
        if self.debug:
            problems.append("APP_ENV=prod 时 DEBUG 必须为 false")
        if any(
            marker in self.auth.jwt_public_key.lower() for marker in PLACEHOLDER_SECRET_MARKERS
        ):
            problems.append("AUTH__JWT_PUBLIC_KEY 仍是示例占位值，必须替换为真实 RSA 公钥 PEM")
        if self.storage.backend != "postgres":
            problems.append("生产环境 STORAGE__BACKEND 必须为 postgres")
        if "*" in self.cors_origins:
            problems.append("生产环境 CORS_ORIGINS 不允许使用通配符 *")
        llm_key = self.llm.gateway_api_key or self.llm.api_key
        if llm_key is not None and llm_key.get_secret_value().lower().startswith(
            PLACEHOLDER_API_KEY_PREFIXES
        ):
            key_name = "LLM__GATEWAY_API_KEY" if self.llm.gateway_api_key else "LLM__API_KEY"
            problems.append(f"{key_name} 仍是示例占位值，必须替换为真实密钥")
        if self.redis.url is None or not self.redis.required:
            problems.append("生产环境必须配置 REDIS__URL 且 REDIS__REQUIRED=true")
        acceptance_modules = [
            *self.agent.tool_modules,
            *self.agent.hooks_modules,
            *([self.rag.retriever_module] if self.rag.retriever_module else []),
        ]
        if any(module.startswith(ACCEPTANCE_MODULE_PREFIX) for module in acceptance_modules):
            problems.append("生产环境禁止启用 acceptance.* 验收夹具模块，请配置正式实现")
        if self.model_runtime.enabled:
            secret = (
                self.control_plane.client_secret.get_secret_value()
                if self.control_plane.client_secret is not None
                else ""
            )
            if not secret or any(
                marker in secret.lower() for marker in PLACEHOLDER_SECRET_MARKERS
            ):
                problems.append(
                    "启用 MODEL_RUNTIME__ENABLED 时必须配置真实的 CONTROL_PLANE__CLIENT_SECRET"
                )

        if problems:
            raise ValueError("；".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """返回全局唯一配置实例。

    使用 lru_cache 保证只解析一次 .env；测试中可通过 get_settings.cache_clear() 重置。
    """
    # auth 由环境变量注入，mypy 看不到 pydantic-settings 的读取过程
    return Settings()  # type: ignore[call-arg]
