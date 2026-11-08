"""System Prompt 目录化。

为什么不在代码里拼字符串：
1. 提示词改动频繁，放在 `.md` 里可以独立评审与回滚；
2. 多套人格/场景只需新增文件，通过 `AGENT__SYSTEM_PROMPT` 切换；
3. 名称做严格白名单校验，避免通过配置读取目录外的文件。

提示词文件按名称缓存，进程内只读一次；文件缺失或为空时直接报错，
由应用启动阶段暴露问题，而不是等第一个请求才失败。
"""

import re
from functools import lru_cache
from pathlib import Path

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

PROMPTS_DIRECTORY = Path(__file__).with_name("prompts")
# 只允许小写字母、数字与连字符，天然排除 "." 与路径分隔符
PROMPT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class PromptNotFoundError(RuntimeError):
    """提示词名称非法、文件缺失或内容为空。"""


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    """按名称加载提示词内容（不含 `.md` 后缀）。"""
    if not PROMPT_NAME_PATTERN.fullmatch(name):
        raise PromptNotFoundError(f"非法的提示词名称：{name}")

    path = (PROMPTS_DIRECTORY / f"{name}.md").resolve()
    # 双保险：即使白名单被放宽，也不允许跳出提示词目录
    if PROMPTS_DIRECTORY.resolve() not in path.parents:
        raise PromptNotFoundError(f"提示词路径越界：{name}")

    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PromptNotFoundError(f"提示词文件不存在：{name}") from exc

    if not content:
        raise PromptNotFoundError(f"提示词文件为空：{name}")
    return content


def load_system_prompt(name: str | None = None) -> str:
    """加载当前生效的系统提示词，未指定时读取配置。"""
    return load_prompt(name or get_settings().agent.system_prompt)


def load_openui_prompt(name: str | None = None) -> str:
    """加载 OpenUI 组件契约。

    该文件由 `frontend/scripts/generate-openui-prompt.mjs` 生成，禁止手改；
    与基础提示词共用同一套名称白名单与缓存。
    """
    return load_prompt(name or get_settings().openui.prompt_name)


def compose_openui_system_prompt(base_prompt: str) -> str:
    """在基础人格提示词后追加 OpenUI 契约与输出规模限制。

    只在 `OPENUI__ENABLED=true` 时调用；关闭时完全不拼接，保证模型行为
    与接入前一致。规模限制来自配置，避免把块数上限写死在生成的契约文件里。
    """
    max_blocks = get_settings().openui.max_blocks
    contract = load_openui_prompt()
    limit = (
        "## 输出规模限制\n"
        f"- 单次回答最多输出 {max_blocks} 个顶层 UI 块，超出时只保留最重要的内容。"
    )
    return f"{base_prompt}\n\n{contract}\n\n{limit}"
