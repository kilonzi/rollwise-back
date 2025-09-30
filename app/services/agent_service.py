from __future__ import annotations

from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.config.context_builder import ContextBuilderService
from app.models import Agent
from app.utils.logging_config import app_logger


class AgentService:
    """Service for managing AI agents and their configurations"""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.context_builder = ContextBuilderService(db_session)

    def build_agent_config(
            self, agent: Agent, phone_number: str = None, conversation_id: str = None
    ) -> Dict[str, Any]:
        """Build Deepgram agent configuration using unified context builder"""
        try:
            return self.context_builder.build_complete_agent_config(
                agent=agent, phone_number=phone_number, conversation_id=conversation_id
            )
        except Exception as e:
            app_logger.error(
                f"Failed to build agent config for agent {agent.id}: {str(e)}"
            )
            # Return a minimal fallback configuration to prevent call drops
            return {
                "agent": {
                    "speak": {
                        "provider": {
                            "type": "deepgram",
                            "model": agent.voice_model or "aura-2-thalia-en",
                        }
                    },
                    "language": agent.language or "en",
                    "think": {
                        "prompt": agent.system_prompt
                                  or "You are a helpful AI assistant.",
                        "functions": [],
                    },
                    "greeting": agent.greeting or "Hello! How can I help you today?",
                }
            }

    def get_agent_by_phone(self, phone_number: str) -> Optional[Agent]:
        """Get agent by phone number"""
        return (
            self.db_session.query(Agent)
            .filter(
                Agent.phone_number == phone_number,
                Agent.active,
            )
            .first()
        )

    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID"""
        return (
            self.db_session.query(Agent)
            .filter(Agent.id == agent_id, Agent.active)
            .first()
        )
