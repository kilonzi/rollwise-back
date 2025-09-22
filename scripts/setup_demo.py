#!/usr/bin/env python3
"""
Demo setup script for RollWise AI Voice Agent Platform

This script creates sample users and agents for testing purposes.
Run this after setting up your environment and database.

Usage:
    python scripts/setup_demo.py
"""

import sys
import os

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import get_db_session, create_tables, User, Agent
from app.utils.logging_config import app_logger as logger


def create_demo_user():
    """Create a demo user"""
    db = get_db_session()
    try:
        user = User(
            name="Bella Rodriguez",
            email="bella@bellasbeauty.com",
            firebase_uid="demo_firebase_uid_123",
            email_verified=True,
            phone_number="+1-555-OWNER",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created user: %s (ID: %s)", user.name, user.id)
        return user
    finally:
        db.close()


def create_demo_agent(user_id: str):
    """Create a demo agent for the user"""
    db = get_db_session()
    try:
        agent = Agent(
            user_id=user_id,
            name="Sofia",
            phone_number="+1234567890",  # Replace with your Twilio number
            greeting="Hello! I'm Sofia from Bella's Beauty Salon. How can I help you today?",
            voice_model="aura-2-thalia-en",
            system_prompt="""You are Sofia, a friendly and professional AI assistant for Bella's Beauty Salon. 
            You help customers with:
            - Booking appointments for services like haircuts, coloring, manicures, facials
            - Answering questions about services and pricing
            - Providing salon information and hours
            - General customer service
            
            Always be warm, professional, and helpful. If you can't handle a request, 
            politely ask the customer to call during business hours to speak with a human staff member.""",
            language="en",
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        logger.info(
            "Created agent: %s (ID: %s) for user %s", agent.name, agent.id, user_id
        )
        return agent
    finally:
        db.close()


def setup_demo():
    """Set up the complete demo environment"""
    logger.info("🚀 Setting up RollWise AI Voice Agent demo...")

    # Create tables first
    create_tables()
    logger.info("✅ Database tables created/verified")

    # Create demo user
    user = create_demo_user()

    # Create demo agent
    agent = create_demo_agent(user.id)

    logger.info("🎉 Demo setup complete!")
    logger.info("📋 Demo Summary:")
    logger.info("👤 User: %s (%s)", user.name, user.email)
    logger.info("🤖 Agent: %s (Phone: %s)", agent.name, agent.phone_number)
    logger.info("📞 Configure Twilio webhook to: /agent/%s/voice", agent.id)
    logger.info("💬 Configure Twilio SMS webhook to: /agent/%s/messages", agent.id)


if __name__ == "__main__":
    setup_demo()
