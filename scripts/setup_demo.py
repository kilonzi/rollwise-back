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

from app.models import get_db_session, create_tables, Tenant, User, Agent


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
        print(f"✅ Created tenant: {tenant.name} (ID: {tenant.id})")
        return tenant
    finally:
        db.close()


def create_demo_user(tenant_id: str):
    """Create a demo user for the tenant"""
    db = get_db_session()
    try:
        user = User(
            tenant_id=tenant_id,
            name="Bella Rodriguez",
            email="bella@bellasbeauty.com",
            phone_number="+1-555-OWNER",
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✅ Created user: {user.name} (ID: {user.id})")
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
        print(f"✅ Created agent: {agent.name} (ID: {agent.id})")
        print(f"📞 Agent phone number: {agent.phone_number}")
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
        print(f"✅ Created second tenant: {tenant.name} (ID: {tenant.id})")

        # Create user for second tenant
        user = User(
            tenant_id=tenant.id,
            name="Mike Johnson",
            email="mike@mikesauto.com",
            phone_number="+1-555-MIKE",
            role="admin",
        )
        db.add(user)

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

        print(f"✅ Created second agent: {agent.name} (ID: {agent.id})")
        print(f"📞 Second agent phone number: {agent.phone_number}")
        return tenant, user, agent
    finally:
        db.close()


def main():
    """Main setup function"""
    print("🚀 Setting up RollWise Multi-Tenant Demo Data")
    print("=" * 50)

    # Ensure database tables exist
    create_tables()
    print("✅ Database tables verified")

    # Create first demo tenant and agent
    print("\n📋 Creating Demo Tenant #1:")
    tenant1 = create_demo_tenant()
    create_demo_user(tenant1.id)
    agent1 = create_demo_agent(tenant1.id)

    # Create second demo tenant and agent
    print("\n📋 Creating Demo Tenant #2:")
    tenant2, user2, agent2 = create_second_demo_tenant()

    print("\n" + "=" * 50)
    print("🎉 Demo setup complete!")
    print("\n📊 Summary:")
    print("   • Tenants created: 2")
    print("   • Users created: 2")
    print("   • Agents created: 2")

    print("\n🔧 Next Steps:")
    print("1. Update your Twilio webhook URLs:")
    print(
        f"   - Agent 1 ({agent1.name}): https://your-domain.com/agent/{agent1.id}/voice"
    )
    print(
        f"   - Agent 2 ({agent2.name}): https://your-domain.com/agent/{agent2.id}/voice"
    )
    print("")
    print("2. Test the agents:")
    print(f"   - Call {agent1.phone_number} for {tenant1.name}")
    print(f"   - Call {agent2.phone_number} for {tenant2.name}")
    print("")
    print("3. View admin API at: http://localhost:8090/admin/")
    print("4. View API docs at: http://localhost:8090/docs")

    print("\n⚠️  Remember to:")
    print("   - Replace phone numbers with your actual Twilio numbers")
    print("   - Set your BASE_URL in .env to your actual domain/ngrok URL")
    print("   - Configure your Deepgram API key")


if __name__ == "__main__":
    main()
