from typing import Dict, Any

from app.models.database import get_db_session
from app.services.collection_service import CollectionService


async def search_collection_tool(
        agent_id: str,
        collection_name: str,
        query: str,
        limit: int = 10
) -> Dict[str, Any]:
    """
    Search a specific document collection for relevant information.

    Use this function to search through uploaded documents, text files, PDFs, or CSV data
    that has been organized into collections. Each collection represents a specific
    knowledge area or document type.

    Args:
        agent_id: ID of the agent (automatically injected)
        collection_name: Name of the collection to search (e.g., 'restaurant_menu', 'delivery_policies')
        query: What you're looking for in natural language
        limit: Maximum number of results to return (default 10, max 50)

    Returns:
        Relevant text chunks with metadata from the specified collection
    """
    try:
        db_session = get_db_session()
        try:
            collection_service = CollectionService(db_session)
            result = collection_service.search_collection(
                agent_id=agent_id,
                collection_name=collection_name,
                query=query,
                limit=min(limit, 50)  # Cap at 50 as specified
            )

            if result["success"] and result.get("results"):
                # Format results for agent consumption
                formatted_results = []
                for item in result["results"]:
                    formatted_results.append({
                        "content": item["text"],
                        "relevance_score": item.get("relevance_score", 0),
                        "source_section": item.get("metadata", {}).get("source_section", ""),
                        "content_type": item.get("metadata", {}).get("content_type", ""),
                        "chunk_index": item.get("metadata", {}).get("chunk_index", 0)
                    })

                return {
                    "success": True,
                    "collection_name": collection_name,
                    "data": formatted_results,
                    "count": len(formatted_results),
                    "message": f"Found {len(formatted_results)} relevant results in '{collection_name}' collection"
                }
            else:
                error_msg = result.get("error", "No results found")
                return {
                    "success": False,
                    "collection_name": collection_name,
                    "data": [],
                    "count": 0,
                    "message": f"No results found in '{collection_name}': {error_msg}"
                }
        finally:
            db_session.close()

    except Exception as e:
        return {
            "success": False,
            "collection_name": collection_name,
            "data": [],
            "count": 0,
            "error": str(e),
            "message": f"Error searching collection '{collection_name}': {str(e)}"
        }


async def hangup_function(reason: str = "conversation_complete") -> Dict[str, Any]:
    """
    Signal to end the conversation and close the connection.

    Use this function when:
    - The conversation has naturally concluded
    - User hasn't responded after asking "Are you there?" or similar
    - User explicitly says goodbye or indicates they want to end the call
    - You've provided all requested information and no further assistance is needed

    Args:
        reason: Brief reason for hanging up (e.g., "conversation_complete", "user_inactive", "user_goodbye")

    Returns:
        Success confirmation that will trigger connection closure
    """
    return {
        "success": True,
        "action": "hangup",
        "reason": reason,
        "message": f"Ending conversation: {reason}"
    }


FUNCTION_MAP = {
    "search_collection": search_collection_tool,
    "hangup_function": hangup_function,
}
