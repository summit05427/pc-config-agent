"""Agent Profile 加载、校验与工具集语义测试。"""

from pathlib import Path

import pytest

from app.agent.profiles import (
    ProfileConfigError,
    ProfileNotFoundError,
    get_profile_store,
    load_profiles,
    resolve_profile,
    resolve_profile_tools,
)
from app.agent.registry import list_tool_specs


def _write_yaml(directory: Path, file_name: str, content: str) -> Path:
    path = directory / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_default_profile_reproduces_legacy_behavior() -> None:
    """缺省 Profile 必须与改造前一致：默认提示词、全部工具、无模型覆盖。"""
    profile = resolve_profile(None)

    assert profile.id == "default"
    assert profile.system_prompt == "default"
    assert profile.tools is None
    assert profile.model.default_key is None
    assert profile.model.temperature is None
    assert profile.model.max_tokens is None
    assert profile.context.max_tokens is None


def test_example_writer_profile_is_loaded() -> None:
    """示例 Profile 证明人格、工具集与模型参数可以由 YAML 控制。"""
    profile = resolve_profile("writer")

    assert profile.display_name == "写作助手"
    assert profile.system_prompt == "writer"
    assert profile.tools == []
    assert profile.model.temperature == 0.8
    assert profile.model.max_tokens == 3000
    assert profile.context.max_tokens == 8000


def test_unknown_profile_raises() -> None:
    with pytest.raises(ProfileNotFoundError):
        resolve_profile("missing_agent")


def test_new_yaml_is_discovered_without_core_changes(tmp_path: Path) -> None:
    """新增 Profile 只需新增 1 个 YAML（提示词复用已有文件）。"""
    directory = tmp_path / "agents"
    _write_yaml(
        directory,
        "reviewer.yaml",
        "\n".join(
            [
                "id: reviewer",
                "display_name: 评审助手",
                "system_prompt: writer",
                "tools:",
                "  - get_current_time",
            ]
        ),
    )

    profiles = load_profiles(directory)

    assert set(profiles) == {"reviewer"}
    assert profiles["reviewer"].tools == ["get_current_time"]


def test_nested_example_directories_are_loaded() -> None:
    store = get_profile_store()

    assert {"default", "writer"} <= set(store)


def test_profile_id_must_match_file_name(tmp_path: Path) -> None:
    directory = tmp_path / "agents"
    _write_yaml(
        directory,
        "renamed.yaml",
        "id: other\ndisplay_name: 文件名不一致\n",
    )

    with pytest.raises(ProfileConfigError, match="id 必须与文件名一致"):
        load_profiles(directory)


def test_missing_prompt_fails_with_file_name(tmp_path: Path) -> None:
    directory = tmp_path / "agents"
    _write_yaml(
        directory,
        "ghost.yaml",
        "id: ghost\ndisplay_name: 幽灵\nsystem_prompt: missing-prompt\n",
    )

    with pytest.raises(ProfileConfigError, match="ghost.yaml"):
        load_profiles(directory)


def test_unknown_tool_fails_with_registered_list(tmp_path: Path) -> None:
    directory = tmp_path / "agents"
    _write_yaml(
        directory,
        "tool_user.yaml",
        "id: tool_user\ndisplay_name: 工具用户\ntools:\n  - not_registered_tool\n",
    )

    with pytest.raises(ProfileConfigError, match="not_registered_tool"):
        load_profiles(directory)


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "agents"
    _write_yaml(
        directory,
        "typo.yaml",
        "id: typo\ndisplay_name: 拼写错误\ntemprature: 0.5\n",
    )

    with pytest.raises(ProfileConfigError, match="temprature"):
        load_profiles(directory)


def test_duplicate_id_across_directories_fails(tmp_path: Path) -> None:
    directory = tmp_path / "agents"
    _write_yaml(directory / "a", "dup.yaml", "id: dup\ndisplay_name: 重复 A\n")
    _write_yaml(directory / "b", "dup.yaml", "id: dup\ndisplay_name: 重复 B\n")

    with pytest.raises(ProfileConfigError, match="Profile id 重复"):
        load_profiles(directory)


def test_empty_profiles_directory_fails(tmp_path: Path) -> None:
    directory = tmp_path / "empty"
    directory.mkdir()

    with pytest.raises(ProfileConfigError, match="目录为空"):
        load_profiles(directory)


def test_missing_profiles_directory_fails(tmp_path: Path) -> None:
    with pytest.raises(ProfileConfigError, match="目录不存在"):
        load_profiles(tmp_path / "missing")


def test_profile_tools_semantics() -> None:
    """省略 tools = 全部工具，[] = 不绑定工具，列表 = 仅绑定列出的工具。"""
    all_tools = [tool.name for tool in resolve_profile_tools(resolve_profile(None))]
    assert all_tools == [spec.tool.name for spec in list_tool_specs()]

    assert resolve_profile_tools(resolve_profile("writer")) == []

    subset_profile = resolve_profile(None).model_copy(update={"tools": ["get_current_time"]})
    assert [tool.name for tool in resolve_profile_tools(subset_profile)] == [
        "get_current_time"
    ]
