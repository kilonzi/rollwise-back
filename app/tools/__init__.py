from .registry import ToolRegistry, tool
from .business_tools import register_business_tools

# Create global registry instance (kept for backward compatibility)
tool_registry = ToolRegistry()

# Register business tools (legacy system)
register_business_tools(tool_registry)

__all__ = ["tool_registry", "tool", "ToolRegistry"]
