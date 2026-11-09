"""pc-config 脚本测试的公共设置。

pytest 会先加载本文件，因此测试模块可以直接 import scripts/pc-config 下的脚本，
与 `python -m unittest discover` 的 `sys.path` 处理保持一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPT_DIR.parents[1]

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
