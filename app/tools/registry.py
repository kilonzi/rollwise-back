import inspect
from typing import Dict, Callable, Any, List

from app.models.database import get_db, ToolCall
from app.tools.calendar_tools import (
    create_calendar_event_function,
    cancel_calendar_event_function,
    search_calendar_events_function,
    update_calendar_event_function,
    list_calendar_events_function
)
from app.utils.logging_config import app_logger as logger


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_descriptions: Dict[str, Dict[str, Any]] = {}

    def register(
        self, name: str, description: str = "", parameters: Dict[str, Any] = None
    ):
        def decorator(func: Callable):
            self.tools[name] = func
            self.tool_descriptions[name] = {
                "name": name,
                "description": description,
                "parameters": parameters or self._extract_parameters(func),
            }
            return func

        return decorator

    @staticmethod
    def _extract_parameters(func: Callable) -> Dict[str, Any]:
        """Extract parameter information from function signature"""
        sig = inspect.signature(func)
        parameters = {}

        for param_name, param in sig.parameters.items():
            if param_name in ["args", "conversation_id", "db"]:
                continue

            param_info = {"type": "string"}
            if param.annotation != inspect.Parameter.empty:
                if param.annotation is int:
                    param_info["type"] = "integer"
                elif param.annotation is bool:
                    param_info["type"] = "boolean"
                elif param.annotation is float:
                    param_info["type"] = "number"

            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default

            parameters[param_name] = param_info

        return {"type": "object", "properties": parameters}

    async def execute_tool(
        self, name: str, args: Dict[str, Any], conversation_id: str
    ) -> Dict[str, Any]:
        """Execute a tool and log the action"""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found"}

        try:
            # Add conversation_id to args
            args["conversation_id"] = conversation_id

            # Execute the tool
            result = await self.tools[name](args)

            # Log the action
            self._log_action(conversation_id, name, args, result, "success")

            return result

        except Exception as e:
            error_result = {"error": str(e)}
            self._log_action(conversation_id, name, args, error_result, "failed")
            return error_result

    def _log_action(
        self,
        conversation_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        status: str,
    ):
        """Log tool execution to database"""
        db = None
        try:
            db = next(get_db())
            tool_call = ToolCall(
                conversation_id=conversation_id,
                tool_name=tool_name,
                parameters=args,
                result=result,
                status=status,
            )
            db.add(tool_call)
            db.commit()
        except Exception as e:
            logger.exception("Failed to log action: %s", e)
        finally:
            if db:
                db.close()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions for the agent"""
        return list(self.tool_descriptions.values())

    def list_tools(self) -> List[str]:
        """Get list of available tool names"""
        return list(self.tools.keys())


def tool(name: str, description: str = "", parameters: Dict[str, Any] = None):
    """Decorator to register a tool"""

    def decorator(func: Callable):
        # This will be used by the global registry
        func._tool_name = name
        func._tool_description = description
        func._tool_parameters = parameters
        return func

    return decorator


# Global registry instance
global_registry = ToolRegistry()

# Calendar tool definitions
CALENDAR_TOOLS = {
    "create_calendar_event": create_calendar_event_function(),
    "cancel_calendar_event": cancel_calendar_event_function(),
    "search_calendar_events": search_calendar_events_function(),
    "update_calendar_event": update_calendar_event_function(),
    "list_calendar_events": list_calendar_events_function()
}

def get_calendar_tool_definitions() -> List[Dict[str, Any]]:
    """Get all calendar tool definitions"""
    return list(CALENDAR_TOOLS.values())

def get_tool_definition(tool_name: str) -> Dict[str, Any]:
    """Get definition for a specific tool"""
    if tool_name in CALENDAR_TOOLS:
        return CALENDAR_TOOLS[tool_name]
    return global_registry.tool_descriptions.get(tool_name, {})
