"""
工具路由

提供 /tools/list、/tools/execute 端点。
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("/list")
async def tools_list():
    """列出所有可用工具"""
    try:
        from tools import get_registry
        registry = get_registry()
        tools = []
        for name, tool in registry._tools.items():
            definition = tool.get_definition()
            tools.append({
                "name": definition.name,
                "description": definition.description,
                "parameters": [
                    {"name": p.name, "type": p.type, "description": p.description, "required": p.required}
                    for p in definition.parameters
                ],
            })
        return {"tools": tools}
    except Exception as e:
        logger.error("Tools list failed: %s", e, exc_info=True)
        return {"error": str(e)}


@router.post("/execute")
async def tools_execute(tool_name: str, arguments: dict):
    """执行工具"""
    try:
        from tools import get_registry
        registry = get_registry()
        tool = registry.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}
        result = await tool.execute(**arguments)
        return {"result": result.content, "success": result.success}
    except Exception as e:
        logger.error("Tool execution failed: %s", e, exc_info=True)
        return {"error": str(e)}
