"""
Legacy agent functions converted to the new tools registry system.
"""

from typing import Dict, Any

from app.tools.registry import global_registry, tool
from app.utils.logging_config import app_logger


# Register all legacy tools with the global registry
def register_legacy_tools():
    """Register all legacy agent functions with the global registry"""
    tools_to_register = []  # Empty list since hangup_function is removed

    for tool_func in tools_to_register:
        global_registry.register(
            name=tool_func._tool_name,
            description=tool_func._tool_description,
            parameters=tool_func._tool_parameters,
        )(tool_func)

    app_logger.info(f"Registered {len(tools_to_register)} legacy tools")


# Auto-register when module is imported
register_legacy_tools()
