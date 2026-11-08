"""生成 Solo 模式的 .env.solo：注入本地自签 RSA 密钥，供 agent-service 的 dev-token 使用。

用法（从仓库根）：
    uv --directory agent-service run python ../scripts/generate_solo_env.py
    uv --directory agent-service run python ../scripts/generate_solo_env.py --force

模板见 `.env.solo.example`；`.env.solo` 已被 .gitignore 忽略，不得提交。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / ".env.solo.example"
TARGET_PATH = REPO_ROOT / ".env.solo"


def _single_line_pem(pem: str) -> str:
    """写成单行：换行用字面量 \\n，agent-service 启动时会还原。"""
    return pem.strip().replace("\n", "\\n")


def main(*, force: bool) -> int:
    if not TEMPLATE_PATH.exists():
        print(f"缺少模板文件：{TEMPLATE_PATH}")
        return 1
    if TARGET_PATH.exists() and not force:
        print(".env.solo 已存在；如需覆盖请加 --force")
        return 1

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    content = content.replace("__DEV_PRIVATE_KEY__", _single_line_pem(private_pem))
    content = content.replace("__DEV_PUBLIC_KEY__", _single_line_pem(public_pem))
    TARGET_PATH.write_text(content, encoding="utf-8")

    print("已生成 .env.solo")
    print("下一步：编辑 .env.solo 填入 LLM_API_KEY，然后执行")
    print("  docker compose --env-file .env.solo up -d --build agent-service")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 Solo 模式的 .env.solo")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 .env.solo")
    raise SystemExit(main(force=parser.parse_args().force))
