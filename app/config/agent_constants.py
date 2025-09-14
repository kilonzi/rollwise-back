VOICE = "aura-2-thalia-en"

# this gets updated by the agent template
FIRST_MESSAGE = ""

# audio settings
USER_AUDIO_SAMPLE_RATE = 48000
USER_AUDIO_SECS_PER_CHUNK = 0.05
USER_AUDIO_SAMPLES_PER_CHUNK = round(USER_AUDIO_SAMPLE_RATE * USER_AUDIO_SECS_PER_CHUNK)

AGENT_AUDIO_SAMPLE_RATE = 16000
AGENT_AUDIO_BYTES_PER_SEC = 2 * AGENT_AUDIO_SAMPLE_RATE

VOICE_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

# Template for the prompt that will be formatted with current date
PROMPT_TEMPLATE = """

CURRENT DATE AND TIME CONTEXT:
Today is {current_date}. Use this as context when discussing appointments and inquiries. When mentioning dates to customers, use relative terms like "tomorrow", "next Tuesday", or "last week" when the dates are within 7 days of today.

PERSONALITY & TONE:
- Be warm, professional, and conversational
- Use natural, flowing speech (avoid bullet points or listing)
- Show empathy and patience
- Use your available tools to help customers effectively

AVAILABLE TOOLS:
You have access to business data search capabilities. When customers ask about:
- Client information: search the "clients" dataset
- Business hours: search the "hours" dataset
- Pricing/Services: search the "pricing" or "inventory" datasets
- Policies: search the "policies" dataset

TOOL USAGE GUIDELINES:
- Always use tools when customers ask for specific information
- Be conversational and natural - don't mention technical terms like "datasets"
- If a search returns no results, politely inform the customer and offer alternatives
- Search with relevant keywords from what the customer says

EXAMPLES OF GOOD RESPONSES:
✓ "Let me look that up for you... I can see you have John Smith's contact information here."
✓ "Based on our hours, we're open Monday through Friday from 9 AM to 6 PM."
✓ "I found your pricing for that service - it's $25 for a basic haircut."

EXAMPLES OF WHAT TO SEARCH:
- Customer asks "What are your hours?" → search "hours" dataset
- Customer asks "Do you have John's number?" → search "clients" with "John"
- Customer asks "How much for a haircut?" → search "pricing" with "haircut"
- Customer asks "What services do you offer?" → search "inventory" or "pricing" with return_all=true

Remember: Use the search_agent_dataset tool whenever customers ask about specific business information.
"""

# Function definitions that will be sent to the Voice Agent API
FUNCTION_DEFINITIONS = [
    {
        "name": "search_agent_dataset",
        "description": """Search business datasets (clients, hours, inventory, pricing, policies, etc.).
        Use this function when customers ask about specific business information.

        Dataset types available:
        - "clients": Customer contact information, names, phones, emails
        - "hours": Business operating hours and availability
        - "pricing": Service prices, rates, and cost information
        - "inventory": Available services, products, or offerings
        - "policies": Business rules, procedures, and policies

        Examples:
        - Customer asks "What are your hours?" → use label="hours"
        - Customer asks "Do you have John's number?" → use label="clients", query="John"
        - Customer asks "How much for a haircut?" → use label="pricing", query="haircut"
        - Customer asks "What services do you offer?" → use label="inventory", return_all=true
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Dataset to search (clients, hours, inventory, pricing, policies, etc.)",
                    "enum": ["clients", "hours", "pricing", "inventory", "policies", "services", "appointments"]
                },
                "query": {
                    "type": "string",
                    "description": "Search query - use keywords from customer's question (names, services, etc.). Leave empty to get all results."
                },
                "return_all": {
                    "type": "boolean",
                    "description": "Set to true to return all records (useful for hours, full price lists, etc.)",
                    "default": False
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (ignored if return_all is true)",
                    "default": 5
                }
            },
            "required": ["label"]
        }
    }
]

AUDIO_SETTINGS = {
    "input": {
        "encoding": "linear16",
        "sample_rate": USER_AUDIO_SAMPLE_RATE,
    },
    "output": {
        "encoding": "linear16",
        "sample_rate": AGENT_AUDIO_SAMPLE_RATE,
        "container": "none",
    },
}

LISTEN_SETTINGS = {
    "provider": {
        "type": "deepgram",
        "model": "nova-3",
    }
}

def get_think_settings():
    """Get think settings with function definitions"""
    return {
        "provider": {
            "type": "open_ai",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
        },
        "prompt": PROMPT_TEMPLATE,
        "functions": FUNCTION_DEFINITIONS,
    }

THINK_SETTINGS = get_think_settings()

SPEAK_SETTINGS = {
    "provider": {
        "type": "deepgram",
        "model": VOICE,
    }
}

AGENT_SETTINGS = {
    "language": "en",
    "listen": LISTEN_SETTINGS,
    "think": THINK_SETTINGS,
    "speak": SPEAK_SETTINGS,
    "greeting": FIRST_MESSAGE,
}

SETTINGS = {"type": "Settings", "audio": AUDIO_SETTINGS, "agent": AGENT_SETTINGS}