from typing import Dict, Any
from app.services.business_dataset_service import search_agent_dataset
from app.services.collection_service import CollectionService
from app.tools.calendar_tools import CalendarTools
from app.models.database import get_db_session


async def search_business_knowledge_base_tool(
    tenant_id: str,
    agent_id: str,
    label: str,
    query: str = "",
    top_k: int = 5,
    return_all: bool = False
) -> Dict[str, Any]:
    """Search business knowledge base using ChromaDB (for static business information only, NOT appointments)"""
    try:
        result = search_agent_dataset(
            tenant_id=tenant_id,
            agent_id=agent_id,
            label=label,
            query=query,
            top_k=top_k,
            return_all=return_all
        )

        # Format results for agent consumption
        if result["success"] and result.get("results"):
            documents = result["results"].get("documents", [])
            metadatas = result["results"].get("metadatas", [])

            if documents and len(documents) > 0:
                # Combine documents with metadata for better context
                formatted_results = []
                docs = documents[0]  # ChromaDB returns nested lists
                metas = metadatas[0] if metadatas else []

                for i, doc in enumerate(docs):
                    meta = metas[i] if i < len(metas) else {}
                    formatted_results.append({
                        "content": doc,
                        "metadata": meta
                    })

                return {
                    "success": True,
                    "data": formatted_results,
                    "count": len(formatted_results),
                    "message": f"Found {len(formatted_results)} results for '{label}'"
                }

        return {
            "success": True,
            "data": [],
            "count": 0,
            "message": f"No results found for '{label}'"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "count": 0,
            "message": f"Error searching '{label}': {str(e)}"
        }


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


# Map function names to their implementations
# Calendar tool wrapper functions for agent use
async def create_calendar_event_tool(**kwargs) -> Dict[str, Any]:
    """Create calendar event wrapper for agent use"""
    db_session = get_db_session()
    try:
        calendar_tools = CalendarTools(db_session)
        return calendar_tools.create_calendar_event(**kwargs)
    finally:
        db_session.close()

async def list_calendar_events_tool(**kwargs) -> Dict[str, Any]:
    """List calendar events wrapper for agent use"""
    db_session = get_db_session()
    try:
        calendar_tools = CalendarTools(db_session)
        return calendar_tools.list_calendar_events(**kwargs)
    finally:
        db_session.close()

async def cancel_calendar_event_tool(**kwargs) -> Dict[str, Any]:
    """Cancel calendar event wrapper for agent use"""
    db_session = get_db_session()
    try:
        calendar_tools = CalendarTools(db_session)
        return calendar_tools.cancel_calendar_event(**kwargs)
    finally:
        db_session.close()

FUNCTION_MAP = {
    "search_business_knowledge_base": search_business_knowledge_base_tool,
    "search_agent_dataset": search_business_knowledge_base_tool,  # Legacy alias for backward compatibility
    "search_collection": search_collection_tool,
    "create_calendar_event": create_calendar_event_tool,
    "list_calendar_events": list_calendar_events_tool,
    "cancel_calendar_event": cancel_calendar_event_tool,
    "hangup_function": hangup_function,
}