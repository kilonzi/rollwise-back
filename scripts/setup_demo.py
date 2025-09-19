#!/usr/bin/env python3
"""
Demo setup script for RollWise Multi-Tenant AI Voice Agent Platform

This script creates sample tenants, users, and agents for testing purposes.
Run this after setting up your environment and database.

Usage:
    python scripts/setup_demo.py
"""

import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import get_db_session, create_tables, Tenant, User, Agent, UserTenant
from app.utils.logging_config import app_logger as logger


def create_demo_tenant():
    """Create a demo tenant"""
    db = get_db_session()
    try:
        tenant = Tenant(
            name="Bella's Beauty Salon",
            business_type="Beauty & Wellness",
            phone_number="+1-555-BEAUTY",
            email="contact@bellasbeauty.com",
            address="123 Main St, Anytown, ST 12345",
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        logger.info("Created tenant: %s (ID: %s)", tenant.name, tenant.id)
        return tenant
    finally:
        db.close()


def create_demo_user(tenant_id: str):
    """Create a demo user for the tenant"""
    db = get_db_session()
    try:
        # In a real app, you'd hash a password. For this demo, we'll use a placeholder.
        # Note: The User model itself doesn't have a tenant_id. The link is via UserTenant.
        user = User(
            name="Bella Rodriguez",
            email="bella@bellasbeauty.com",
            password_hash="a_placeholder_password_hash",  # Add required password_hash
            phone_number="+1-555-OWNER",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Now, create the link in the UserTenant table
        user_tenant = UserTenant(
            user_id=user.id,
            tenant_id=tenant_id,
            role="admin"
        )
        db.add(user_tenant)
        db.commit()

        logger.info("Created user: %s (ID: %s) and linked to tenant %s", user.name, user.id, tenant_id)
        return user
    finally:
        db.close()


def create_demo_agent(tenant_id: str):
    """Create a demo agent for the tenant"""
    db = get_db_session()
    try:
        agent = Agent(
            tenant_id=tenant_id,
            name="Sofia",
            phone_number="+1234567890",  # Replace with your Twilio number
            greeting="Hello! I'm Sofia from Bella's Beauty Salon. How can I help you today?",
            voice_model="aura-2-thalia-en",
            system_prompt="""You are Sofia, the AI assistant for Bella's Beauty Salon.

Your role is to:
- Greet customers warmly and professionally
- Help schedule appointments for hair, nails, facials, and other beauty services
- Answer questions about our services and prices
- Collect customer contact information
- Provide business hours and location information
- Transfer complex requests to human staff when needed

Always be friendly, knowledgeable, and represent Bella's Beauty Salon with excellence.""",
            language="en",
            tools=[
                "book_appointment",
                "save_contact_info",
                "get_business_hours",
                "check_availability",
                "transfer_to_human",
                "get_caller_history",
            ],
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        logger.info("Created agent: %s (ID: %s)", agent.name, agent.id)
        logger.info("Agent phone number: %s", agent.phone_number)
        return agent
    finally:
        db.close()


def create_second_demo_tenant():
    """Create a second demo tenant for multi-tenant testing"""
    db = get_db_session()
    try:
        tenant = Tenant(
            name="Mike's Auto Repair",
            business_type="Automotive",
            phone_number="+1-555-REPAIR",
            email="info@mikesauto.com",
            address="456 Garage Ave, Cartown, ST 54321",
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        logger.info("Created second tenant: %s (ID: %s)", tenant.name, tenant.id)

        # Create user for second tenant
        user = User(
            name="Mike Johnson",
            email="mike@mikesauto.com",
            password_hash="a_placeholder_password_hash", # Add required password_hash
            phone_number="+1-555-MIKE",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Link user to the new tenant
        user_tenant = UserTenant(
            user_id=user.id,
            tenant_id=tenant.id,
            role="admin"
        )
        db.add(user_tenant)
        db.commit()


        # Create agent for second tenant
        agent = Agent(
            tenant_id=tenant.id,
            name="Alex",
            phone_number="+0987654321",  # Replace with your second Twilio number
            greeting="Hi there! I'm Alex from Mike's Auto Repair. How can I assist you with your vehicle today?",
            voice_model="aura-2-thalia-en",
            system_prompt="""You are Alex, the AI assistant for Mike's Auto Repair.

Your role is to:
- Help customers schedule automotive service appointments
- Provide information about repair services, oil changes, inspections
- Collect customer vehicle information and contact details
- Answer questions about pricing and services
- Provide business hours and location information
- Transfer complex technical questions to our mechanics

Always be helpful, knowledgeable about automotive services, and professional.""",
            language="en",
            tools=[
                "book_appointment",
                "save_contact_info",
                "get_business_hours",
                "check_availability",
                "transfer_to_human",
            ],
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        logger.info("Created second agent: %s (ID: %s)", agent.name, agent.id)
        logger.info("Second agent phone number: %s", agent.phone_number)
        return tenant, user, agent
    finally:
        db.close()


def main():
    """Main setup function"""
    logger.info("Setting up RollWise Multi-Tenant Demo Data")
    logger.info("%s", "=" * 50)

    # Ensure database tables exist
    create_tables()
    logger.info("Database tables verified")

    # Create first demo tenant and agent
    logger.info("Creating Demo Tenant #1:")
    tenant1 = create_demo_tenant()
    create_demo_user(tenant1.id)
    agent1 = create_demo_agent(tenant1.id)

    # Create second demo tenant and agent
    logger.info("Creating Demo Tenant #2:")
    tenant2, user2, agent2 = create_second_demo_tenant()

    logger.info("%s", "=" * 50)
    logger.info("Demo setup complete!")
    logger.info("Summary:")
    logger.info("   • Tenants created: 2")
    logger.info("   • Users created: 2")
    logger.info("   • Agents created: 2")

    logger.info("Next Steps:")
    logger.info("1. Update your Twilio webhook URLs:")
    logger.info("   - Agent 1 (%s): https://your-domain.com/agent/%s/voice", agent1.name, agent1.id)
    logger.info("   - Agent 2 (%s): https://your-domain.com/agent/%s/voice", agent2.name, agent2.id)
    logger.info("2. Test the agents:")
    logger.info("   - Call %s for %s", agent1.phone_number, tenant1.name)
    logger.info("   - Call %s for %s", agent2.phone_number, tenant2.name)
    logger.info("3. View admin API at: http://localhost:8090/admin/")
    logger.info("4. View API docs at: http://localhost:8090/docs")

    logger.warning("Remember to:")
    logger.warning("   - Replace phone numbers with your actual Twilio numbers")
    logger.warning("   - Set your BASE_URL in .env to your actual domain/ngrok URL")
    logger.warning("   - Configure your Deepgram API key")


if __name__ == "__main__":
    main()
