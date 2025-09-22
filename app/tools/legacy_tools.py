"""
Legacy agent functions converted to the new tools registry system.
"""

from typing import Dict, Any

from app.models.database import get_db_session
from app.services.collection_service import CollectionService
from app.tools.registry import global_registry, tool
from app.utils.logging_config import app_logger


@tool(
    name="search_collection",
    description="Search a specific document collection for relevant information",
    parameters={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "ID of the agent (automatically injected)",
            },
            "collection_name": {
                "type": "string",
                "description": "Name of the collection to search (e.g., 'restaurant_menu', 'delivery_policies')",
            },
            "query": {
                "type": "string",
                "description": "What you're looking for in natural language",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default 10, max 50)",
                "default": 10,
            },
        },
        "required": ["agent_id", "collection_name", "query"],
    },
)
async def search_collection_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search a specific document collection for relevant information.

    Use this function to search through uploaded documents, text files, PDFs, or CSV data
    that has been organized into collections. Each collection represents a specific
    knowledge area or document type.
    """
    try:
        agent_id = args.get("agent_id")
        collection_name = args.get("collection_name")
        query = args.get("query")
        limit = args.get("limit", 10)

        if not agent_id or not collection_name or not query:
            return {
                "success": False,
                "error": "Missing required parameters: agent_id, collection_name, or query",
            }

        db_session = get_db_session()
        try:
            collection_service = CollectionService(db_session)
            result = collection_service.search_collection(
                agent_id=agent_id,
                collection_name=collection_name,
                query=query,
                limit=min(limit, 50),  # Cap at 50 as specified
            )

            if result["success"] and result.get("results"):
                # Format results for agent consumption
                formatted_results = []
                for item in result["results"]:
                    formatted_results.append(
                        {
                            "content": item["text"],
                            "relevance_score": item.get("relevance_score", 0),
                            "source_section": item.get("metadata", {}).get(
                                "source_section", ""
                            ),
                            "content_type": item.get("metadata", {}).get(
                                "content_type", ""
                            ),
                            "chunk_index": item.get("metadata", {}).get(
                                "chunk_index", 0
                            ),
                        }
                    )

                return {
                    "success": True,
                    "collection_name": collection_name,
                    "data": formatted_results,
                    "count": len(formatted_results),
                    "message": f"Found {len(formatted_results)} relevant results in '{collection_name}' collection",
                }
            else:
                error_msg = result.get("error", "No results found")
                return {
                    "success": False,
                    "collection_name": collection_name,
                    "data": [],
                    "count": 0,
                    "message": f"No results found in '{collection_name}': {error_msg}",
                }
        finally:
            db_session.close()

    except Exception as e:
        app_logger.error(f"Error searching collection '{collection_name}': {str(e)}")
        return {
            "success": False,
            "collection_name": collection_name,
            "data": [],
            "count": 0,
            "error": str(e),
            "message": f"Error searching collection '{collection_name}': {str(e)}",
        }


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
    tools_to_register = [search_collection_tool, hangup_function]

    for tool_func in tools_to_register:
        global_registry.register(
            name=tool_func._tool_name,
            description=tool_func._tool_description,
            parameters=tool_func._tool_parameters,
        )(tool_func)

    app_logger.info(f"Registered {len(tools_to_register)} legacy tools")


# Auto-register when module is imported
register_legacy_tools()
