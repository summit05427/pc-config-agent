"""客户端声明的用户偏好。

偏好只影响「本轮怎么回答」：拼进系统提示词、决定是否注入历史消息。
它不参与鉴权、不构成任何授权依据——服务端只做长度与枚举校验，
绝不能因为 `preferences` 里的内容放宽任何权限判断。

字段取值与 Java 侧 `user_preferences`、前端设置页保持一致：
- `reply_language`：`auto` / `zh-CN` / `en-US`
- `response_style`：`concise` / `balanced` / `detailed`
"""

from typing import Literal

from pydantic import BaseModel, Field

INSTRUCTIONS_MAX_LENGTH = 1000

ReplyLanguage = Literal["auto", "zh-CN", "en-US"]
ResponseStyle = Literal["concise", "balanced", "detailed"]

# auto 表示「不额外约束」，因此不出现在提示词里
LANGUAGE_HINTS: dict[str, str] = {
    "zh-CN": "请始终使用简体中文回答。",
    "en-US": "Always answer in English.",
}

STYLE_HINTS: dict[str, str] = {
    "concise": "回答尽量简短：先给结论，避免冗长铺垫。",
    "balanced": "回答保持适中长度：先给结论，再补充必要细节。",
    "detailed": "回答可以更详细：必要时分步骤说明并给出示例。",
}


class ChatPreferences(BaseModel):
    """一次对话请求携带的偏好；全部字段可选，缺省即不改变当前行为。"""

    instructions: str | None = Field(
        default=None,
        max_length=INSTRUCTIONS_MAX_LENGTH,
        description="用户自定义指令",
    )
    reply_language: ReplyLanguage | None = Field(default=None, description="回复语言")
    response_style: ResponseStyle | None = Field(default=None, description="回复风格")
    use_history: bool = Field(default=True, description="是否把历史消息注入本轮上下文")


def build_preference_prompt(preferences: ChatPreferences | None) -> str | None:
    """把偏好渲染成追加到系统提示词的片段。

    @param preferences 请求携带的偏好，可为 None
    @return 渲染后的片段；没有任何有效偏好时返回 None，表示不改变系统提示词
    """
    if preferences is None:
        return None

    lines: list[str] = []
    instructions = (preferences.instructions or "").strip()
    if instructions:
        lines.append(f"用户自定义指令（优先遵守）：{instructions}")

    language_hint = LANGUAGE_HINTS.get(preferences.reply_language or "")
    if language_hint:
        lines.append(language_hint)

    style_hint = STYLE_HINTS.get(preferences.response_style or "")
    if style_hint:
        lines.append(style_hint)

    if not lines:
        return None
    return "## 用户偏好\n" + "\n".join(f"- {line}" for line in lines)
