"""
Memory API Router for CRUD operations on agent memories
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.schemas.memory_schemas import (
    MemoryResponse,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemorySearchRequest
)
from app.models import get_db, Memory, Agent
from app.services.memory_service import MemoryService

router = APIRouter()


def _serialize_memory(memory: Memory) -> dict:
    """Serialize Memory object to dictionary"""
    return {
        "id": memory.id,
        "agent_id": memory.agent_id,
        "conversation_id": memory.conversation_id,
        "message_id": memory.message_id,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "memory_metadata": memory.memory_metadata,
        "importance": memory.importance,
        "embedding": memory.embedding,
        "coach_id": memory.coach_id,
        "last_used_at": memory.last_used_at.isoformat() if memory.last_used_at else None,
        "active": memory.active,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
        "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
    }


@router.get(
    "/{agent_id}/memories", response_model=List[MemoryResponse]
)
async def get_agent_memories(
    agent_id: str,
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    importance_min: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum importance threshold"),
    importance_max: Optional[float] = Query(None, ge=0.0, le=1.0, description="Maximum importance threshold"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of memories to return"),
    offset: int = Query(0, ge=0, description="Number of memories to skip"),
    order_by: str = Query("importance_desc", description="Order by field"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get memories for a specific agent with optional filters"""
    # Verify agent exists and user has access
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    # Build search request
    search_req = MemorySearchRequest(
        agent_id=agent_id,
        memory_type=memory_type,
        importance_min=importance_min,
        importance_max=importance_max,
        limit=limit,
        offset=offset,
        order_by=order_by
    )

    memories = MemoryService.search_memories(db, search_req)
    return [_serialize_memory(memory) for memory in memories]


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    update_last_used: bool = Query(True, description="Update last_used_at timestamp"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific memory by ID"""
    memory = MemoryService.get_memory(db, memory_id, update_last_used=update_last_used)

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found"
        )

    return _serialize_memory(memory)


@router.post("/{agent_id}/memories", response_model=MemoryResponse)
async def create_memory(
    agent_id: str,
    memory_data: MemoryCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new memory for an agent"""
    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    # Ensure agent_id matches the route parameter
    memory_data.agent_id = agent_id

    # Set coach_id to current user if not provided
    if not memory_data.coach_id:
        memory_data.coach_id = current_user.id

    try:
        memory = MemoryService.create_memory(db, memory_data)
        return _serialize_memory(memory)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create memory: {str(e)}"
        )


@router.put("/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    memory_data: MemoryUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing memory"""
    try:
        memory = MemoryService.update_memory(db, memory_id, memory_data)

        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found"
            )

        return _serialize_memory(memory)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory: {str(e)}"
        )


@router.delete("/memories/{memory_id}")
async def delete_memory(
    memory_id: str,
    soft_delete: bool = Query(True, description="Soft delete (deactivate) vs hard delete"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a memory (soft delete by default)"""
    try:
        success = MemoryService.delete_memory(db, memory_id, soft_delete=soft_delete)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found"
            )

        delete_type = "deactivated" if soft_delete else "permanently deleted"
        return {"message": f"Memory {delete_type} successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory: {str(e)}"
        )


@router.get("/{agent_id}/memories/types/{memory_type}", response_model=List[MemoryResponse])
async def get_memories_by_type(
    agent_id: str,
    memory_type: str,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of memories to return"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all memories of a specific type for an agent"""
    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    memories = MemoryService.get_memories_by_type(db, agent_id, memory_type, limit=limit)
    return [_serialize_memory(memory) for memory in memories]


@router.get("/{agent_id}/memories/important", response_model=List[MemoryResponse])
async def get_important_memories(
    agent_id: str,
    importance_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum importance threshold"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of memories to return"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the most important memories for an agent"""
    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    memories = MemoryService.get_important_memories(
        db, agent_id, importance_threshold=importance_threshold, limit=limit
    )
    return [_serialize_memory(memory) for memory in memories]


@router.get("/conversations/{conversation_id}/memories", response_model=List[MemoryResponse])
async def get_conversation_memories(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all memories linked to a specific conversation"""
    from app.models import Conversation

    # Verify conversation exists
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.active == True
    ).first()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    memories = MemoryService.get_memories_by_conversation(db, conversation_id)
    return [_serialize_memory(memory) for memory in memories]


@router.patch("/memories/{memory_id}/importance")
async def update_memory_importance(
    memory_id: str,
    new_importance: float = Query(..., ge=0.0, le=1.0, description="New importance score"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the importance score of a memory"""
    try:
        memory = MemoryService.update_memory_importance(db, memory_id, new_importance)

        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found"
            )

        return {
            "message": "Memory importance updated successfully",
            "memory_id": memory_id,
            "new_importance": memory.importance
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory importance: {str(e)}"
        )


@router.post("/{agent_id}/memories/bulk", response_model=List[MemoryResponse])
async def bulk_create_memories(
    agent_id: str,
    memories_data: List[MemoryCreateRequest],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create multiple memories in a single transaction"""
    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    # Set agent_id and default coach_id for all memories
    for memory_data in memories_data:
        memory_data.agent_id = agent_id
        if not memory_data.coach_id:
            memory_data.coach_id = current_user.id

    try:
        memories = MemoryService.bulk_create_memories(db, memories_data)
        return [_serialize_memory(memory) for memory in memories]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk create memories: {str(e)}"
        )


@router.get("/{agent_id}/memories/stats")
async def get_memory_stats(
    agent_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get statistics about an agent's memories"""
    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )

    try:
        stats = MemoryService.get_memory_stats(db, agent_id)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory stats: {str(e)}"
        )
