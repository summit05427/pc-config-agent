"""错误码注册表：源码字面量必须已登记，码值风格统一。"""

import re
from pathlib import Path

import pytest

from app.core.error_codes import ERROR_CODES, build_http_error_code, is_registered

APP_DIRECTORY = Path(__file__).resolve().parents[1] / "app"

# 只匹配 `code="..."` 字面量；控制面透传的动态码不在扫描范围
CODE_LITERAL_PATTERN = re.compile(r'\bcode\s*=\s*"([a-z0-9_]+)"')
CODE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _literal_codes() -> dict[str, list[str]]:
    """收集 app/ 下所有 code 字面量，按码值记录出现的文件便于定位。"""
    found: dict[str, list[str]] = {}
    for path in sorted(APP_DIRECTORY.rglob("*.py")):
        content = path.read_text(encoding="utf-8")
        for match in CODE_LITERAL_PATTERN.finditer(content):
            found.setdefault(match.group(1), []).append(path.name)
    return found


def test_all_literal_codes_are_registered() -> None:
    """新增错误码必须先登记，否则测试失败。"""
    unregistered = {
        code: files
        for code, files in _literal_codes().items()
        if not is_registered(code)
    }
    assert not unregistered, f"未登记的错误码：{unregistered}"


def test_registry_codes_use_snake_case() -> None:
    invalid = [code for code in ERROR_CODES if not CODE_NAME_PATTERN.fullmatch(code)]
    assert not invalid, f"错误码必须是小写 snake_case：{invalid}"


def test_registry_entries_have_descriptions() -> None:
    missing = [code for code, description in ERROR_CODES.items() if not description.strip()]
    assert not missing, f"错误码缺少说明：{missing}"


def test_unregistered_code_is_rejected() -> None:
    assert not is_registered("totally_unknown_code")


@pytest.mark.parametrize("status_code", [401, 404, 405, 422, 500])
def test_framework_http_codes_follow_pattern(status_code: int) -> None:
    """框架级错误不在字典里逐条登记，但必须能被识别为已登记。"""
    assert is_registered(build_http_error_code(status_code))
