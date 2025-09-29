"""
Memory Service for managing agent memories with CRUD operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc

from app.models.database import Memory
from app.utils.logging_config import app_logger


class MemoryCreateRequest(BaseModel):
    agent_id: str
    content: str
    memory_type: str = "lesson"  # lesson, feedback, summary, rule, fact
    memory_metadata: Optional[Dict[str, Any]] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    coach_id: Optional[str] = None
    embedding: Optional[List[float]] = None


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    memory_type: Optional[str] = None
    memory_metadata: Optional[Dict[str, Any]] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    coach_id: Optional[str] = None
    embedding: Optional[List[float]] = None
    active: Optional[bool] = None


class MemorySearchRequest(BaseModel):
    agent_id: str
    memory_type: Optional[str] = None
    importance_min: Optional[float] = None
    importance_max: Optional[float] = None
    content_contains: Optional[str] = None
    coach_id: Optional[str] = None
    conversation_id: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    last_used_after: Optional[datetime] = None
    last_used_before: Optional[datetime] = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    order_by: str = Field(default="importance_desc", pattern="^(importance_desc|importance_asc|created_desc|created_asc|last_used_desc|last_used_asc)$")


class MemoryService:
    """Service for managing agent memories with full CRUD operations"""

    @staticmethod
    def create_memory(db: Session, req: MemoryCreateRequest) -> Memory:
        """Create a new memory record"""
        try:
            memory_data = req.dict(exclude_unset=True)
            memory = Memory(**memory_data)

            db.add(memory)
            db.commit()
            db.refresh(memory)

            app_logger.info(f"Created memory {memory.id} for agent {req.agent_id}")
            return memory

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to create memory for agent {req.agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_memory(db: Session, memory_id: str, update_last_used: bool = True) -> Optional[Memory]:
        """Get a specific memory by ID"""
        try:
            memory = db.query(Memory).filter(
                Memory.id == memory_id,
                Memory.active == True
            ).first()

            if memory and update_last_used:
                memory.last_used_at = func.now()
                db.commit()

            return memory

        except Exception as e:
            app_logger.error(f"Failed to get memory {memory_id}: {str(e)}")
            raise

    @staticmethod
    def update_memory(db: Session, memory_id: str, req: MemoryUpdateRequest) -> Optional[Memory]:
        """Update an existing memory"""
        try:
            memory = db.query(Memory).filter(
                Memory.id == memory_id,
                Memory.active == True
            ).first()

            if not memory:
                return None

            update_data = req.dict(exclude_unset=True, exclude_none=True)

            for field, value in update_data.items():
                setattr(memory, field, value)

            memory.updated_at = func.now()
            db.commit()
            db.refresh(memory)

            app_logger.info(f"Updated memory {memory_id}")
            return memory

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to update memory {memory_id}: {str(e)}")
            raise

    @staticmethod
    def delete_memory(db: Session, memory_id: str, soft_delete: bool = True) -> bool:
        """Delete a memory (soft delete by default)"""
        try:
            memory = db.query(Memory).filter(Memory.id == memory_id).first()

            if not memory:
                return False

            if soft_delete:
                memory.active = False
                memory.updated_at = func.now()
            else:
                db.delete(memory)

            db.commit()

            delete_type = "soft deleted" if soft_delete else "hard deleted"
            app_logger.info(f"Memory {memory_id} {delete_type}")
            return True

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to delete memory {memory_id}: {str(e)}")
            raise

    @staticmethod
    def retrieve_memories(
        db: Session,
        agent_id: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
        update_last_used: bool = True
    ) -> List[Memory]:
        """
        Retrieve memories for an agent (your original function enhanced)

        Args:
            db: Database session
            agent_id: Agent ID to get memories for
            memory_type: Optional filter by memory type
            limit: Maximum number of memories to return
            update_last_used: Whether to update last_used_at timestamp

        Returns:
            List of Memory objects ordered by importance desc, created_at desc
        """
        try:
            query = db.query(Memory).filter(
                Memory.agent_id == agent_id,
                Memory.active == True
            )

            if memory_type:
                query = query.filter(Memory.memory_type == memory_type)

            memories = query.order_by(
                Memory.importance.desc(),
                Memory.created_at.desc()
            ).limit(limit).all()

            if update_last_used and memories:
                now = func.now()
                for mem in memories:
                    mem.last_used_at = now
                db.commit()

            app_logger.info(f"Retrieved {len(memories)} memories for agent {agent_id}")
            return memories

        except Exception as e:
            app_logger.error(f"Failed to retrieve memories for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def search_memories(db: Session, req: MemorySearchRequest) -> List[Memory]:
        """Advanced search for memories with multiple filters"""
        try:
            query = db.query(Memory).filter(
                Memory.agent_id == req.agent_id,
                Memory.active == True
            )

            # Apply filters
            if req.memory_type:
                query = query.filter(Memory.memory_type == req.memory_type)

            if req.importance_min is not None:
                query = query.filter(Memory.importance >= req.importance_min)

            if req.importance_max is not None:
                query = query.filter(Memory.importance <= req.importance_max)

            if req.content_contains:
                query = query.filter(Memory.content.ilike(f"%{req.content_contains}%"))

            if req.coach_id:
                query = query.filter(Memory.coach_id == req.coach_id)

            if req.conversation_id:
                query = query.filter(Memory.conversation_id == req.conversation_id)

            if req.created_after:
                query = query.filter(Memory.created_at >= req.created_after)

            if req.created_before:
                query = query.filter(Memory.created_at <= req.created_before)

            if req.last_used_after:
                query = query.filter(Memory.last_used_at >= req.last_used_after)

            if req.last_used_before:
                query = query.filter(Memory.last_used_at <= req.last_used_before)

            # Apply ordering
            if req.order_by == "importance_desc":
                query = query.order_by(desc(Memory.importance))
            elif req.order_by == "importance_asc":
                query = query.order_by(asc(Memory.importance))
            elif req.order_by == "created_desc":
                query = query.order_by(desc(Memory.created_at))
            elif req.order_by == "created_asc":
                query = query.order_by(asc(Memory.created_at))
            elif req.order_by == "last_used_desc":
                query = query.order_by(desc(Memory.last_used_at))
            elif req.order_by == "last_used_asc":
                query = query.order_by(asc(Memory.last_used_at))

            # Apply pagination
            memories = query.offset(req.offset).limit(req.limit).all()

            app_logger.info(f"Search found {len(memories)} memories for agent {req.agent_id}")
            return memories

        except Exception as e:
            app_logger.error(f"Failed to search memories for agent {req.agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_memories_by_type(db: Session, agent_id: str, memory_type: str, limit: int = 50) -> List[Memory]:
        """Get all memories of a specific type for an agent"""
        try:
            memories = db.query(Memory).filter(
                Memory.agent_id == agent_id,
                Memory.memory_type == memory_type,
                Memory.active == True
            ).order_by(
                desc(Memory.importance),
                desc(Memory.created_at)
            ).limit(limit).all()

            return memories

        except Exception as e:
            app_logger.error(f"Failed to get {memory_type} memories for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def get_memories_by_conversation(db: Session, conversation_id: str) -> List[Memory]:
        """Get all memories linked to a specific conversation"""
        try:
            memories = db.query(Memory).filter(
                Memory.conversation_id == conversation_id,
                Memory.active == True
            ).order_by(desc(Memory.created_at)).all()

            return memories

        except Exception as e:
            app_logger.error(f"Failed to get memories for conversation {conversation_id}: {str(e)}")
            raise

    @staticmethod
    def get_important_memories(
        db: Session,
        agent_id: str,
        importance_threshold: float = 0.7,
        limit: int = 20
    ) -> List[Memory]:
        """Get the most important memories for an agent"""
        try:
            memories = db.query(Memory).filter(
                Memory.agent_id == agent_id,
                Memory.importance >= importance_threshold,
                Memory.active == True
            ).order_by(
                desc(Memory.importance),
                desc(Memory.last_used_at)
            ).limit(limit).all()

            return memories

        except Exception as e:
            app_logger.error(f"Failed to get important memories for agent {agent_id}: {str(e)}")
            raise

    @staticmethod
    def update_memory_importance(db: Session, memory_id: str, new_importance: float) -> Optional[Memory]:
        """Update the importance score of a memory"""
        try:
            memory = db.query(Memory).filter(
                Memory.id == memory_id,
                Memory.active == True
            ).first()

            if not memory:
                return None

            old_importance = memory.importance
            memory.importance = max(0.0, min(1.0, new_importance))  # Clamp between 0 and 1
            memory.updated_at = func.now()

            db.commit()
            db.refresh(memory)

            app_logger.info(f"Updated memory {memory_id} importance from {old_importance} to {memory.importance}")
            return memory

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to update importance for memory {memory_id}: {str(e)}")
            raise

    @staticmethod
    def bulk_create_memories(db: Session, memories_data: List[MemoryCreateRequest]) -> List[Memory]:
        """Create multiple memories in a single transaction"""
        try:
            memories = []
            for req in memories_data:
                memory_data = req.dict(exclude_unset=True)
                memory = Memory(**memory_data)
                memories.append(memory)

            db.add_all(memories)
            db.commit()

            for memory in memories:
                db.refresh(memory)

            app_logger.info(f"Bulk created {len(memories)} memories")
            return memories

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to bulk create memories: {str(e)}")
            raise

    @staticmethod
    def get_memory_stats(db: Session, agent_id: str) -> Dict[str, Any]:
        """Get statistics about an agent's memories"""
        try:
            from sqlalchemy import func as sql_func

            total_memories = db.query(Memory).filter(
                Memory.agent_id == agent_id,
                Memory.active == True
            ).count()

            # Count by type
            type_counts = db.query(
                Memory.memory_type,
                sql_func.count(Memory.id).label('count')
            ).filter(
                Memory.agent_id == agent_id,
                Memory.active == True
            ).group_by(Memory.memory_type).all()

            # Average importance
            avg_importance = db.query(
                sql_func.avg(Memory.importance)
            ).filter(
                Memory.agent_id == agent_id,
                Memory.active == True
            ).scalar() or 0.0

            # Most recent memory
            latest_memory = db.query(Memory).filter(
                Memory.agent_id == agent_id,
                Memory.active == True
            ).order_by(desc(Memory.created_at)).first()

            return {
                "total_memories": total_memories,
                "memory_types": {t.memory_type: t.count for t in type_counts},
                "average_importance": round(float(avg_importance), 3),
                "latest_memory_date": latest_memory.created_at if latest_memory else None
            }

        except Exception as e:
            app_logger.error(f"Failed to get memory stats for agent {agent_id}: {str(e)}")
            raise
