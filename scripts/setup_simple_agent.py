#!/usr/bin/env python3
"""
Simple script showing how to set up an agent with dataset search capability.
This uses the new Deepgram-aligned system.
"""

import requests
from pathlib import Path
from app.utils.logging_config import app_logger as logger

# Configuration
BASE_URL = "http://localhost:8090"
AGENT_ID = "your-agent-id-here"  # Replace with actual agent ID

# Sample client data CSV content
CLIENT_DATA = """name,phone,email,service,notes
John Smith,+1234567890,john@email.com,Haircut,Regular customer - prefers short cuts
Jane Doe,+1234567891,jane@email.com,Color,Allergic to ammonia-based products
Mike Johnson,+1234567892,mike@email.com,Wash & Cut,Prefers appointments after 3 PM
Sarah Wilson,+1234567893,sarah@email.com,Highlights,VIP customer - books monthly"""

HOURS_DATA = """day,hours,notes
Monday,9:00 AM - 6:00 PM,Regular hours
Tuesday,9:00 AM - 6:00 PM,Regular hours
Wednesday,9:00 AM - 6:00 PM,Regular hours
Thursday,9:00 AM - 8:00 PM,Extended hours
Friday,9:00 AM - 8:00 PM,Extended hours
Saturday,8:00 AM - 5:00 PM,Weekend hours
Sunday,Closed,Closed for family time"""

PRICING_DATA = """service,price,duration,description
Haircut,$25,30 min,Basic cut and style
Wash & Cut,$35,45 min,Shampoo + cut + style
Color,$65,90 min,Full color service
Highlights,$85,120 min,Partial or full highlights
Style Only,$20,20 min,Blow dry and style
Beard Trim,$15,15 min,Beard shaping and trim"""


def upload_datasets():
    """Upload sample business datasets"""
    logger.info("Uploading business datasets...")

    datasets = [
        ("clients", CLIENT_DATA),
        ("hours", HOURS_DATA),
        ("pricing", PRICING_DATA)
    ]

    for label, data in datasets:
        # Write temporary file
        temp_file = Path(f"temp_{label}.csv")
        temp_file.write_text(data)

        try:
            # Upload to agent
            with open(temp_file, 'rb') as f:
                files = {"file": (f"sample_{label}.csv", f, "text/csv")}
                form_data = {
                    "label": label,
                    "replace_existing": "true"
                }

                response = requests.post(
                    f"{BASE_URL}/datasets/upload/{AGENT_ID}",
                    files=files,
                    data=form_data
                )

            if response.status_code == 200:
                result = response.json()
                logger.info("Uploaded %s: %s records", label, result.get('record_count'))
            else:
                logger.error("Failed to upload %s: %s", label, response.text)

        finally:
            # Clean up
            if temp_file.exists():
                temp_file.unlink()

    logger.info("Upload complete!")


def test_search():
    """Test the search functionality"""
    logger.info("Testing search...")

    test_queries = [
        {"label": "clients", "query": "John", "description": "Search for John"},
        {"label": "hours", "return_all": True, "description": "Get all hours"},
        {"label": "pricing", "query": "haircut", "description": "Find haircut price"}
    ]

    for query in test_queries:
        logger.info("%s", query['description'])
        response = requests.post(
            f"{BASE_URL}/datasets/search/{AGENT_ID}",
            json=query
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("success") and result.get("count", 0) > 0:
                logger.info("Found %s results", result.get('count'))
            else:
                logger.info("No results found")
        else:
            logger.error("Error searching: %s", response.status_code)


def show_examples():
    """Show usage examples"""
    logger.info("VOICE INTERACTION EXAMPLES")

    logger.info("Your agent can now answer:")
    logger.info("Customer: 'What are your hours?'")
    logger.info("Agent: Searches 'hours' dataset and responds with business hours")
    logger.info("Customer: 'Do you have John Smith's phone number?'")
    logger.info("Agent: Searches 'clients' for 'John Smith' and provides contact info")
    logger.info("Customer: 'How much is a haircut?'")
    logger.info("Agent: Searches 'pricing' for 'haircut' and provides price")
    logger.info("Customer: 'What services do you offer?'")
    logger.info("Agent: Searches 'pricing' dataset and lists all services")

    logger.info("How it works:")
    logger.info("• Agent automatically uses search_agent_dataset function")
    logger.info("• Deepgram calls the function with appropriate parameters")
    logger.info("• ChromaDB searches your uploaded data")
    logger.info("• Agent responds naturally with the information")

    logger.info("Your agent is ready at:")
    logger.info("   Voice: %s/agent/%s/voice", BASE_URL, AGENT_ID)
    logger.info("   WebSocket: wss://your-domain/ws/%s/twilio", AGENT_ID)


def main():
    """Main setup function"""
    logger.info("RollWise Agent Setup (Deepgram System)")

    if not AGENT_ID or AGENT_ID == "your-agent-id-here":
        logger.error("Please update AGENT_ID in the script with your actual agent ID")
        return

    # Upload datasets
    upload_datasets()

    # Test search
    test_search()

    # Show examples
    show_examples()

    logger.info("Setup complete! Your agent now has dataset search capabilities.")
    logger.info("The agent will automatically use the search_agent_dataset function when customers ask questions about your business data.")


if __name__ == "__main__":
    main()