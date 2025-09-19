from __future__ import annotations

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from app.models import Agent, Tenant
from app.utils.agent_config_builder import AgentConfigBuilder
from app.services.calendar_service import CalendarService
from app.utils.logging_config import app_logger


class AgentService:
    """Service for managing AI agents and their configurations"""

    @staticmethod
    def build_agent_config(agent: Agent, customer_context: str = "", dataset_details: str = "", collection_details: str = "") -> Dict[str, Any]:
        """Build Deepgram agent configuration from database agent record with comprehensive context"""
        try:
            # Use the AgentConfigBuilder to build the configuration with comprehensive context
            return AgentConfigBuilder.build_agent_config(
                agent,
                customer_context=customer_context,
                collection_details=collection_details
            )
        except Exception as e:
            app_logger.error(f"Failed to build agent config for agent {agent.id}: {str(e)}")
            # Return a minimal fallback configuration to prevent call drops
            return {
                "agent": {
                    "speak": {
                        "provider": {
                            "model": agent.voice_model or "aura-2-thalia-en"
                        }
                    },
                    "language": agent.language or "en",
                    "think": {
                        "prompt": agent.system_prompt or "You are a helpful AI assistant.",
                        "functions": []
                    },
                    "greeting": agent.greeting or "Hello! How can I help you today?"
                }
            }

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
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            # Check if phone number is already in use
            existing_agent = db.query(Agent).filter(
                Agent.phone_number == phone_number,
                Agent.active,
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
            Agent.active
        )

        if tenant_id:
            query = query.filter(Agent.tenant_id == tenant_id)

        return query.all()

    @staticmethod
    def create_agent_with_calendar(db: Session,
                                 tenant_id: str,
                                 name: str,
                                 greeting: str,
                                 system_prompt: str,
                                 voice_model: str = "aura-2-thalia-en",
                                 language: str = "en",
                                 business_hours: Optional[Dict[str, Any]] = None,
                                 default_slot_duration: int = 30,
                                 max_slot_appointments: int = 1,
                                 buffer_time: int = 15) -> Dict[str, Any]:
        """Create a new agent with integrated calendar"""
        try:
            # Create agent record
            agent_id = str(uuid.uuid4())

            # Default business hours if not provided
            if business_hours is None:
                business_hours = {
                    "start": "09:00",
                    "end": "17:00",
                    "timezone": "UTC",
                    "days": [1, 2, 3, 4, 5]  # Monday to Friday
                }

            agent = Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name=name,
                greeting=greeting,
                system_prompt=system_prompt,
                voice_model=voice_model,
                language=language,
                business_hours=business_hours,
                default_slot_duration=default_slot_duration,
                max_slot_appointments=max_slot_appointments,
                buffer_time=buffer_time,
                tools=["create_calendar_event", "cancel_calendar_event", "search_calendar_events",
                       "update_calendar_event", "list_calendar_events"]  # Include calendar tools
            )

            # Add to database but don't commit yet
            db.add(agent)
            db.flush()  # Get the ID without committing

            # Create Google Calendar for the agent
            calendar_service = CalendarService()
            try:
                calendar_id = calendar_service.create_agent_calendar(agent_id, name)
                agent.calendar_id = calendar_id
                app_logger.info(f"Created calendar {calendar_id} for agent {agent_id}")
            except Exception as calendar_error:
                app_logger.warning(f"Failed to create calendar for agent {agent_id}: {str(calendar_error)}")
                # Continue without calendar - can be added later
                pass

            # Commit the transaction
            db.commit()
            db.refresh(agent)

            app_logger.info(f"Created agent {agent_id} with calendar integration")

            return {
                "success": True,
                "agent": {
                    "id": agent.id,
                    "name": agent.name,
                    "calendar_id": agent.calendar_id,
                    "business_hours": agent.business_hours,
                    "default_slot_duration": agent.default_slot_duration,
                    "max_slot_appointments": agent.max_slot_appointments,
                    "buffer_time": agent.buffer_time,
                    "has_calendar": agent.calendar_id is not None
                }
            }

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to create agent with calendar: {str(e)}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def setup_agent_calendar(db: Session, agent_id: str) -> Dict[str, Any]:
        """Setup calendar for an existing agent that doesn't have one"""
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id, Agent.active).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            if agent.calendar_id:
                return {"success": False, "error": "Agent already has a calendar"}

            # Create Google Calendar for the agent
            calendar_service = CalendarService()
            calendar_id = calendar_service.create_agent_calendar(agent_id, agent.name)

            # Update agent with calendar ID
            agent.calendar_id = calendar_id

            # Add calendar tools if not already present
            current_tools = agent.tools or []
            calendar_tools = ["create_calendar_event", "cancel_calendar_event", "search_calendar_events",
                            "update_calendar_event", "list_calendar_events"]

            for tool in calendar_tools:
                if tool not in current_tools:
                    current_tools.append(tool)

            agent.tools = current_tools
            agent.updated_at = datetime.utcnow()

            db.commit()

            app_logger.info(f"Setup calendar {calendar_id} for existing agent {agent_id}")

            return {
                "success": True,
                "calendar_id": calendar_id,
                "message": "Calendar setup successfully"
            }

        except Exception as e:
            db.rollback()
            app_logger.error(f"Failed to setup calendar for agent {agent_id}: {str(e)}")
            return {"success": False, "error": str(e)}