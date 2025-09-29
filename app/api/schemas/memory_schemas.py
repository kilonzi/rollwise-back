"""
Pydantic schemas for Memory API endpoints
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class MemoryResponse(BaseModel):
    """Response schema for Memory objects"""
    id: str
    agent_id: str
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    memory_type: str
    content: str
    memory_metadata: Optional[Dict[str, Any]] = None
    importance: float
    embedding: Optional[List[float]] = None
    # coach_id: Optional[str] = None
    last_used_at: Optional[str] = None
    active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class MemoryCreateRequest(BaseModel):
    """Request schema for creating new memories"""
    agent_id: str
    content: str = Field(..., min_length=1, max_length=10000)
    memory_type: str = Field(default="lesson", pattern="^(lesson|feedback|summary|rule|fact)$")
    memory_metadata: Optional[Dict[str, Any]] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    coach_id: Optional[str] = None
    embedding: Optional[List[float]] = None


class MemoryUpdateRequest(BaseModel):
    """Request schema for updating existing memories"""
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    memory_type: Optional[str] = Field(None, pattern="^(lesson|feedback|summary|rule|fact)$")
    memory_metadata: Optional[Dict[str, Any]] = None
    importance: Optional[float] = Field(None, ge=0.0, le=1.0)
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    coach_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    active: Optional[bool] = None


class MemorySearchRequest(BaseModel):
    """Request schema for searching memories"""
    agent_id: str
    memory_type: Optional[str] = None
    importance_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    importance_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    content_contains: Optional[str] = None
    coach_id: Optional[str] = None
    conversation_id: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    last_used_after: Optional[datetime] = None
    last_used_before: Optional[datetime] = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    order_by: str = Field(
        default="importance_desc",
        pattern="^(importance_desc|importance_asc|created_desc|created_asc|last_used_desc|last_used_asc)$"
    )


class MemoryStatsResponse(BaseModel):
    """Response schema for memory statistics"""
    total_memories: int
    memory_types: Dict[str, int]
    average_importance: float
    latest_memory_date: Optional[str] = None
