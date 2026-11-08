"""WP1.1 验收用：与内置工具重名，验证同名冲突会阻止启动。"""

from app.agent.registry import register_tool


@register_tool(
    name="solve_pc_build",
    description="与内置工具重名，用于验证注册表冲突检测。",
)
def conflicting_solve(requirement_json: str) -> str:
    return requirement_json
