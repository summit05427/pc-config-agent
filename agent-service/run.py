"""本地启动入口。

为什么不能直接用 `uvicorn app.main:app`：
Windows 默认事件循环是 ProactorEventLoop，而 psycopg 的异步驱动只支持 SelectorEventLoop。
uvicorn 0.36+ 在 Windows 且未启用子进程时会强制使用 Proactor，仅设置事件循环策略无效。

因此这里两步一起做：
1. 把事件循环策略切到 SelectorEventLoop；
2. 用 loop="none" 让 uvicorn 走默认创建流程，而不是它内置的 Proactor 工厂。
Linux 生产环境不受影响，仍可用 uvicorn 命令行直接启动。
"""

import asyncio
import os
import sys

import uvicorn

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    loop_options = {"loop": "none"} if sys.platform == "win32" else {}

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        **loop_options,
    )
