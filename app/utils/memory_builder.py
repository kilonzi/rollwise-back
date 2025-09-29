"""
Memory context builder utility for agent memories
"""

from typing import Optional, List
from sqlalchemy.orm import Session

from app.models import Agent
from app.services.memory_service import MemoryService
from app.utils.logging_config import app_logger


def build_memory_context(
    db_session: Session,
    agent: Agent,
    conversation_id: Optional[str] = None,
    limit: int = 5
) -> str:
    """
    Build agent memory context from stored memories

    Args:
        db_session: Database session
        agent: Agent object
        conversation_id: Optional current conversation ID to get related memories
        limit: Maximum number of memories to include

    Returns:
        Formatted memory context string
    """
    try:
        # Get important memories first (high importance threshold)
        important_memories = MemoryService.get_important_memories(
            db_session,
            agent_id=agent.id,
            importance_threshold=0.7,
            limit=3
        )

        # Get recent relevant memories
        recent_memories = MemoryService.retrieve_memories(
            db_session,
            agent_id=agent.id,
            limit=limit,
            update_last_used=True
        )

        # Get conversation-specific memories if we have a conversation_id
        conversation_memories = []
        if conversation_id:
            conversation_memories = MemoryService.get_memories_by_conversation(
                db_session,
                conversation_id
            )

        # Combine and deduplicate memories
        all_memories = []
        seen_ids = set()

        # Add important memories first
        for memory in important_memories:
            if memory.id not in seen_ids:
                all_memories.append(memory)
                seen_ids.add(memory.id)

        # Add conversation-specific memories
        for memory in conversation_memories:
            if memory.id not in seen_ids:
                all_memories.append(memory)
                seen_ids.add(memory.id)

        # Add recent memories to fill remaining slots
        remaining_slots = max(0, limit - len(all_memories))
        for memory in recent_memories[:remaining_slots]:
            if memory.id not in seen_ids:
                all_memories.append(memory)
                seen_ids.add(memory.id)

        if not all_memories:
            return ""

        # Format memories into context
        context_parts = [f"AGENT MEMORIES ({len(all_memories)} memories):"]

        # Group memories by type for better organization
        memory_by_type = {}
        for memory in all_memories:
            memory_type = memory.memory_type
            if memory_type not in memory_by_type:
                memory_by_type[memory_type] = []
            memory_by_type[memory_type].append(memory)

        # Format each memory type section
        type_order = ["rule", "lesson", "fact", "feedback", "summary"]  # Priority order

        for memory_type in type_order:
            if memory_type in memory_by_type:
                memories = memory_by_type[memory_type]
                context_parts.append(f"\n{memory_type.upper()}S:")

                for memory in memories:
                    importance_indicator = "🔥" if memory.importance > 0.8 else "⭐" if memory.importance > 0.6 else "💡"
                    context_parts.append(f"{importance_indicator} {memory.content}")

                    # Add metadata if available and relevant
                    if memory.memory_metadata:
                        metadata_str = _format_metadata(memory.memory_metadata)
                        if metadata_str:
                            context_parts.append(f"   Context: {metadata_str}")

        # Handle any remaining memory types not in priority order
        for memory_type, memories in memory_by_type.items():
            if memory_type not in type_order:
                context_parts.append(f"\n{memory_type.upper()}S:")

                for memory in memories:
                    importance_indicator = "🔥" if memory.importance > 0.8 else "⭐" if memory.importance > 0.6 else "💡"
                    context_parts.append(f"{importance_indicator} {memory.content}")

        context_parts.append("\nIMPORTANT: Use these memories to provide personalized, informed service based on past learnings and established rules.")

        return "\n".join(context_parts)

    except Exception as e:
        app_logger.error(f"Error building memory context for agent {agent.id}: {str(e)}")
        return "AGENT MEMORIES: Error retrieving memories"


def build_memory_context_by_type(
    db_session: Session,
    agent: Agent,
    memory_types: List[str],
    limit_per_type: int = 3
) -> str:
    """
    Build memory context for specific memory types

    Args:
        db_session: Database session
        agent: Agent object
        memory_types: List of memory types to include
        limit_per_type: Maximum memories per type

    Returns:
        Formatted memory context string for specific types
    """
    try:
        context_parts = []

        for memory_type in memory_types:
            memories = MemoryService.get_memories_by_type(
                db_session,
                agent_id=agent.id,
                memory_type=memory_type,
                limit=limit_per_type
            )

            if memories:
                context_parts.append(f"{memory_type.upper()}S:")
                for memory in memories:
                    importance_indicator = "🔥" if memory.importance > 0.8 else "⭐" if memory.importance > 0.6 else "💡"
                    context_parts.append(f"{importance_indicator} {memory.content}")
                context_parts.append("")  # Empty line between types

        return "\n".join(context_parts) if context_parts else ""

    except Exception as e:
        app_logger.error(f"Error building typed memory context for agent {agent.id}: {str(e)}")
        return ""


def build_rules_and_lessons_context(db_session: Session, agent: Agent) -> str:
    """
    Build context specifically for rules and lessons (most important for agent behavior)

    Args:
        db_session: Database session
        agent: Agent object

    Returns:
        Formatted context string for rules and lessons only
    """
    try:
        # Get rules (highest priority)
        rules = MemoryService.get_memories_by_type(
            db_session,
            agent_id=agent.id,
            memory_type="rule",
            limit=10  # More rules since they're critical
        )

        # Get important lessons
        lessons = MemoryService.get_memories_by_type(
            db_session,
            agent_id=agent.id,
            memory_type="lesson",
            limit=5
        )

        if not rules and not lessons:
            return ""

        context_parts = ["AGENT RULES & LESSONS:"]

        if rules:
            context_parts.append("\nRULES (MUST FOLLOW):")
            for rule in rules:
                context_parts.append(f"🚨 {rule.content}")

        if lessons:
            context_parts.append("\nLEARNED LESSONS:")
            for lesson in lessons:
                importance_indicator = "🔥" if lesson.importance > 0.8 else "⭐"
                context_parts.append(f"{importance_indicator} {lesson.content}")

        return "\n".join(context_parts)

    except Exception as e:
        app_logger.error(f"Error building rules/lessons context for agent {agent.id}: {str(e)}")
        return ""


def _format_metadata(metadata: dict) -> str:
    """Format memory metadata into readable string"""
    if not metadata:
        return ""

    relevant_fields = []

    # Extract common useful metadata fields
    if "source" in metadata:
        relevant_fields.append(f"from {metadata['source']}")
    if "customer_type" in metadata:
        relevant_fields.append(f"customer: {metadata['customer_type']}")
    if "situation" in metadata:
        relevant_fields.append(f"situation: {metadata['situation']}")
    if "tags" in metadata and isinstance(metadata["tags"], list):
        relevant_fields.append(f"tags: {', '.join(metadata['tags'])}")

    return ", ".join(relevant_fields) if relevant_fields else ""
