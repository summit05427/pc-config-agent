"""Agent Profile：把人格、工具集与模型参数从代码搬到 YAML。

为什么需要 Profile：
1. 一套模板要同时服务写作、客服、数据分析等场景，差异应体现在配置而不是分支代码；
2. 人格、工具绑定与模型参数属于「接入方内容」，不应让接入方改 `app/` 核心；
3. 配置文件优先（ADR-0004）：启动期一次性加载并校验，不做热加载，
   配置错误在进程启动时暴露，而不是请求期才发现。

加载约定：
- 扫描 `AGENT__PROFILES_DIR` 下所有 `*.yaml`（含子目录，便于放示例）；
- 文件名必须与 `id` 一致，避免「文件放错目录」难以排查；
- `tools` 省略 = 绑定注册表全部工具；`tools: []` = 不绑定任何工具；
- 未配置的模型/上下文参数回落到全局 `AGENT__*` / `LLM__*` 配置。
"""

import re
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path

import structlog
import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.prompts import PROMPT_NAME_PATTERN, PromptNotFoundError, load_prompt
from app.agent.registry import (
    TOOL_NAME_PATTERN,
    ToolSpec,
    build_tools,
    ensure_tools_loaded,
    get_default_tools,
    get_tool_spec,
    list_tool_specs,
)
from app.core.config import PROJECT_ROOT, get_settings

logger = structlog.get_logger(__name__)

PROFILE_FILE_SUFFIX = ".yaml"
# 与 ChatRequest.agent_id 保持同一约束：Profile 的 id 就是对外契约
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
# 与 ChatRequest.model 同一约束，保证 Profile 默认模型和请求模型可互相覆盖
MODEL_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9:_.-]*$")
MAX_PROFILE_TOOLS = 32


class ProfileConfigError(RuntimeError):
    """Profile 配置非法；消息必须包含文件、字段与期望值。"""


class ProfileNotFoundError(LookupError):
    """请求了未配置的 agent_id。"""


class ProfileModelSettings(BaseModel):
    """Profile 级模型参数；省略项的语义是「沿用全局配置」。"""

    model_config = ConfigDict(extra="forbid")

    # 平台模型完整引用，如 openai:gpt-4o-mini；按「显式模型」处理，控制面不可达时不降级
    default_key: str | None = Field(default=None, max_length=128)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)


class ProfileContextSettings(BaseModel):
    """Profile 级上下文预算。"""

    model_config = ConfigDict(extra="forbid")

    max_tokens: int | None = Field(default=None, ge=1, le=100_000)


class AgentProfile(BaseModel):
    """一个 Agent 的全部可配置差异。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=64)
    # 指向 app/agent/prompts/<name>.md，复用提示词白名单与缓存
    system_prompt: str = Field(default="default", max_length=64)
    model: ProfileModelSettings = Field(default_factory=ProfileModelSettings)
    # None = 全部工具；[] = 不绑定工具；列表 = 仅绑定列出的工具
    tools: list[str] | None = Field(default=None, max_length=MAX_PROFILE_TOOLS)
    context: ProfileContextSettings = Field(default_factory=ProfileContextSettings)


def _format_validation_error(exc: ValidationError) -> str:
    """把 pydantic 错误压成「字段: 原因」的可读文本，便于直接修 YAML。"""
    details = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        details.append(f"{location}: {error['msg']}")
    return "；".join(details)


def _validate_profile(profile: AgentProfile, path: Path) -> None:
    """语义校验：ID、提示词、工具引用都在启动期失败。"""
    if not PROFILE_ID_PATTERN.fullmatch(profile.id):
        raise ProfileConfigError(
            f"Profile 文件 {path.name} 的 id 非法：{profile.id}"
            "（需以小写字母开头，只含小写字母/数字/下划线/连字符，最长 32）"
        )
    if not PROMPT_NAME_PATTERN.fullmatch(profile.system_prompt):
        raise ProfileConfigError(
            f"Profile {profile.id} 的 system_prompt 非法：{profile.system_prompt}"
        )
    if profile.model.default_key is not None and not MODEL_KEY_PATTERN.fullmatch(
        profile.model.default_key
    ):
        raise ProfileConfigError(
            f"Profile {profile.id} 的 model.default_key 非法：{profile.model.default_key}"
            "（形如 openai:gpt-4o-mini）"
        )

    try:
        load_prompt(profile.system_prompt)
    except PromptNotFoundError as exc:
        raise ProfileConfigError(
            f"Profile 文件 {path.name}（id={profile.id}）的系统提示词不可用：{exc}"
            "（在 app/agent/prompts/ 下新增同名 .md）"
        ) from exc

    for tool_name in profile.tools or ():
        if not TOOL_NAME_PATTERN.fullmatch(tool_name):
            raise ProfileConfigError(
                f"Profile {profile.id} 的工具名非法：{tool_name}"
            )
        if get_tool_spec(tool_name) is None:
            registered = sorted(spec.tool.name for spec in list_tool_specs())
            raise ProfileConfigError(
                f"Profile {profile.id} 引用了未注册的工具：{tool_name}"
                f"（已注册：{', '.join(registered) or '无'}）"
            )


def _load_profile_file(path: Path) -> AgentProfile:
    """读取并校验单个 YAML；任何错误都带上文件名。"""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileConfigError(f"Profile 文件 {path.name} 不是合法 YAML：{exc}") from exc

    if not isinstance(raw, dict):
        raise ProfileConfigError(f"Profile 文件 {path.name} 必须是一个 YAML 映射")

    try:
        profile = AgentProfile.model_validate(raw)
    except ValidationError as exc:
        raise ProfileConfigError(
            f"Profile 文件 {path.name} 校验失败：{_format_validation_error(exc)}"
        ) from exc

    # 文件名与 id 一致，才能保证「新增一个 YAML」就是新增一个 Profile
    if profile.id != path.stem:
        raise ProfileConfigError(
            f"Profile 文件 {path.name} 的 id 必须与文件名一致，当前为 {profile.id}"
        )

    _validate_profile(profile, path)
    return profile


def resolve_profiles_dir(configured: str) -> Path:
    """相对路径按服务根目录解析，保证从任意工作目录启动都能读到。"""
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def load_profiles(directory: Path) -> dict[str, AgentProfile]:
    """加载目录下全部 Profile；空目录、重复 id 都直接失败。"""
    # 工具引用校验依赖注册表，先完成发现（内置 → tools_ext → 配置模块）
    ensure_tools_loaded()

    if not directory.is_dir():
        raise ProfileConfigError(f"Profile 目录不存在：{directory}")

    profiles: dict[str, AgentProfile] = {}
    for path in sorted(directory.rglob(f"*{PROFILE_FILE_SUFFIX}")):
        profile = _load_profile_file(path)
        existing = profiles.get(profile.id)
        if existing is not None:
            raise ProfileConfigError(f"Profile id 重复：{profile.id}（{path.name}）")
        profiles[profile.id] = profile

    if not profiles:
        raise ProfileConfigError(f"Profile 目录为空：{directory}")
    return profiles


@lru_cache(maxsize=1)
def get_profile_store() -> Mapping[str, AgentProfile]:
    """启动期加载一次；配置只在重启后生效（ADR-0004 不做热加载）。"""
    settings = get_settings()
    profiles = load_profiles(resolve_profiles_dir(settings.agent.profiles_dir))
    default_id = settings.agent.default_profile
    if default_id not in profiles:
        raise ProfileConfigError(
            f"默认 Profile 不存在：{default_id}"
            f"（AGENT__DEFAULT_PROFILE；已加载：{', '.join(sorted(profiles))}）"
        )
    logger.info("profiles.loaded", count=len(profiles), default=default_id)
    return profiles


def resolve_profile(agent_id: str | None) -> AgentProfile:
    """请求级 `agent_id` → Profile；缺省使用 `AGENT__DEFAULT_PROFILE`。"""
    store = get_profile_store()
    target = agent_id or get_settings().agent.default_profile
    profile = store.get(target)
    if profile is None:
        raise ProfileNotFoundError(target)
    return profile


def resolve_profile_tools(
    profile: AgentProfile,
    extra_specs: Iterable[ToolSpec] | None = None,
) -> list[BaseTool]:
    """按 Profile 的 `tools` 语义返回治理后的工具列表。

    `extra_specs` 是运行时接入的工具（当前为 MCP）：
    - Profile 省略 `tools`（全部工具）时并入；
    - Profile 显式列出工具名时才可用，避免绕过收窄语义。
    """
    extra = {spec.tool.name: spec for spec in (extra_specs or ())}

    if profile.tools is None:
        return get_default_tools() + build_tools(list(extra.values()))

    specs = []
    for tool_name in profile.tools:
        spec = get_tool_spec(tool_name) or extra.get(tool_name)
        if spec is None:  # 启动期已校验，这里只做防御
            raise ProfileConfigError(f"Profile {profile.id} 引用了未注册的工具：{tool_name}")
        specs.append(spec)
    return build_tools(specs)
