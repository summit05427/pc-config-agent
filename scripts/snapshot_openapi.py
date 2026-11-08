"""生成或校验 agent-service 的 OpenAPI 契约快照。

用法（从仓库根执行）：

    uv --directory agent-service run python ../scripts/snapshot_openapi.py
    uv --directory agent-service run python ../scripts/snapshot_openapi.py --check

为什么用脚本生成快照，而不是读取线上 `/openapi.json`：
生产环境按安全策略关闭了 OpenAPI（`openapi_url=None`），契约只能从代码导出，
不能依赖运行中的服务；快照随代码提交，CI 用它发现契约变更。
"""

import argparse
import json
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1] / "agent-service"
SNAPSHOT_PATH = SERVICE_ROOT / "tests" / "contracts" / "openapi_snapshot.json"


def _ensure_startable_env() -> None:
    """补齐 Settings 导入期必需的最小配置。

    `Settings` 在模块导入时就会构建并校验 PEM 公钥；快照内容与密钥无关，
    因此缺配置时生成一把临时密钥即可，避免脚本依赖本地 `.env`。
    """
    os.environ.setdefault("APP_ENV", "dev")
    if os.environ.get("AUTH__JWT_PUBLIC_KEY"):
        return

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    # 容器里常用单行 PEM，配置层会把它还原成真实换行
    os.environ["AUTH__JWT_PUBLIC_KEY"] = public_pem.replace("\n", "\\n")


def render_snapshot() -> str:
    """按固定格式渲染 OpenAPI 文档；排序保证两次生成逐字节一致。"""
    _ensure_startable_env()
    # `app` 包位于 agent-service 根目录；脚本从仓库任意位置执行都能导入
    sys.path.insert(0, str(SERVICE_ROOT))
    from app.main import app

    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成或校验 agent-service OpenAPI 快照")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只校验，不写文件；快照与代码不一致时返回非 0",
    )
    args = parser.parse_args()

    rendered = render_snapshot()
    if not args.check:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(rendered, encoding="utf-8")
        print(f"OpenAPI 快照已写入 {SNAPSHOT_PATH}")
        return 0

    if not SNAPSHOT_PATH.is_file():
        print(f"缺少 OpenAPI 快照：{SNAPSHOT_PATH}")
        return 1
    if SNAPSHOT_PATH.read_text(encoding="utf-8") != rendered:
        print("OpenAPI 快照与当前代码不一致；如属预期变更，请重新生成并同步 docs/api-contract.md")
        return 1
    print("OpenAPI 快照与当前代码一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
