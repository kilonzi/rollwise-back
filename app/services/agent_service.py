from typing import Dict, Any
from sqlalchemy.orm import Session

from app.models import Agent, Tenant
from app.config.agent_templates import AgentTemplates


class AgentService:
    """Service for managing AI agents and their configurations"""

    def build_agent_config(self, agent: Agent) -> Dict[str, Any]:
        """Build Deepgram agent configuration from database agent record"""

        # Determine industry based on agent or tenant info
        industry = "business_service"  # Default

        # You could add logic here to determine industry from agent.tools or other fields
        # For now, using a simple mapping or default
        if hasattr(agent, 'tenant') and agent.tenant:
            business_type = agent.tenant.business_type
            if business_type:
                # Map business types to industries
                business_type_lower = business_type.lower()
                if "salon" in business_type_lower or "beauty" in business_type_lower:
                    industry = "salon"
                elif "restaurant" in business_type_lower or "food" in business_type_lower:
                    industry = "restaurant"
                elif "health" in business_type_lower or "medical" in business_type_lower:
                    industry = "healthcare"
                elif "retail" in business_type_lower or "store" in business_type_lower:
                    industry = "retail"
                elif "tech" in business_type_lower or "support" in business_type_lower:
                    industry = "tech_support"

        # Get company name from tenant
        company_name = agent.tenant.name if agent.tenant else "Your Business"

        # Create agent template
        template = AgentTemplates(
            industry=industry,
            voiceModel=agent.voice_model,
            company_name=company_name
        )

        # Get configuration for this specific agent
        return template.get_config_for_agent(agent)

    def get_agent_by_phone(self, db: Session, phone_number: str) -> Agent:
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

    def get_agent_by_id(self, db: Session, agent_id: str) -> Agent:
        """Get agent by ID with active tenant check"""
        return (
            db.query(Agent)
            .join(Tenant)
            .filter(Agent.id == agent_id, Agent.active, Tenant.active)
            .first()
        )