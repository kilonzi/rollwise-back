from typing import Dict, Any
from app.services.business_dataset_service import search_agent_dataset


async def search_agent_dataset_tool(
    tenant_id: str,
    agent_id: str,
    label: str,
    query: str = "",
    top_k: int = 5,
    return_all: bool = False
) -> Dict[str, Any]:
    """Search agent datasets using ChromaDB"""
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
FUNCTION_MAP = {
    "search_agent_dataset": search_agent_dataset_tool,
    "hangup_function": hangup_function,
}