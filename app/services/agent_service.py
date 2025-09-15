from __future__ import annotations

from typing import Dict, Any
from sqlalchemy.orm import Session

from app.models import Agent, Tenant
from app.utils.agent_config_builder import AgentConfigBuilder


class AgentService:
    """Service for managing AI agents and their configurations"""

    @staticmethod
    def build_agent_config(agent: Agent) -> Dict[str, Any]:
        """Build Deepgram agent configuration from database agent record"""
        return AgentConfigBuilder.build_agent_config(agent)

    @staticmethod
    def get_agent_by_phone(db: Session, phone_number: str) -> type[Agent] | None:
        """Get agent by phone number with active tenant check"""
        return (
            db.query(Agent)
            .join(Tenant)
            .filter(
                Agent.phone_number == phone_number,
                Agent.active,
                Tenant.active,
            )
            .first()
        )

    @staticmethod
    def get_agent_by_id(db: Session, agent_id: str) -> type[Agent] | None:
        """Get agent by ID with active tenant check"""
        return (
            db.query(Agent)
            .join(Tenant)
            .filter(Agent.id == agent_id, Agent.active, Tenant.active)
            .first()
        )

    @staticmethod
    def assign_phone_number(db: Session, agent_id: str, phone_number: str) -> Dict[str, Any]:
        """Assign a phone number to an agent"""
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active == True).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            # Check if phone number is already in use
            existing_agent = db.query(Agent).filter(
                Agent.phone_number == phone_number,
                Agent.active == True,
                Agent.id != agent_id
            ).first()
            if existing_agent:
                return {"success": False, "error": "Phone number already in use"}

            agent.phone_number = phone_number
            db.commit()

            return {
                "success": True,
                "message": "Phone number assigned successfully",
                "agent_id": agent.id,
                "phone_number": phone_number
            }

        except Exception as e:
            db.rollback()
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_agents_without_phone(db: Session, tenant_id: str = None) -> list[Agent]:
        """Get agents that don't have phone numbers assigned"""
        query = db.query(Agent).filter(
            Agent.phone_number.is_(None),
            Agent.active == True
        )

        if tenant_id:
            query = query.filter(Agent.tenant_id == tenant_id)

        return query.all()