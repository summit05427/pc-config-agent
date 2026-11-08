"""v1 路由聚合层。

所有 v1 模块在这里注册一次，main.py 只挂载 api_router。
后续新增 chat、agents、tools 等模块时，只改这个文件，不动入口。
"""

from fastapi import APIRouter

from app.api.v1 import auth, chat, health, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(sessions.router)
