"""
Legacy agent functions converted to the new tools registry system.
"""

from typing import Dict, Any

from app.tools.registry import global_registry, tool
from app.utils.logging_config import app_logger


@tool(
    name="hangup_function",
    description="Signal to end the conversation and close the connection",
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Brief reason for hanging up (e.g., 'conversation_complete', 'user_inactive', 'user_goodbye')",
                "default": "conversation_complete",
            }
        },
        "required": [],
    },
)
async def hangup_function(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Signal to end the conversation and close the connection.

    Use this function when:
    - The conversation has naturally concluded
    - User hasn't responded after asking "Are you there?" or similar
    - User explicitly says goodbye or indicates they want to end the call
    - You've provided all requested information and no further assistance is needed
    """
    reason = args.get("reason", "conversation_complete")

    return {
        "success": True,
        "action": "hangup",
        "reason": reason,
        "message": f"Ending conversation: {reason}",
    }


# Register all legacy tools with the global registry
def register_legacy_tools():
    """Register all legacy agent functions with the global registry"""
    tools_to_register = [hangup_function]

    for tool_func in tools_to_register:
        global_registry.register(
            name=tool_func._tool_name,
            description=tool_func._tool_description,
            parameters=tool_func._tool_parameters,
        )(tool_func)

    app_logger.info(f"Registered {len(tools_to_register)} legacy tools")


# Auto-register when module is imported
register_legacy_tools()
