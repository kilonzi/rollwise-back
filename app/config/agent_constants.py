VOICE = "aura-2-thalia-en"

# this gets updated by the agent template
FIRST_MESSAGE = ""

# audio settings - optimized for clear voice streaming
# Using 16kHz for both input/output to avoid resampling overhead
# Using 20ms chunks for better real-time performance and reduced latency
USER_AUDIO_SAMPLE_RATE = 8000
USER_AUDIO_SECS_PER_CHUNK = 0.02
AGENT_AUDIO_SAMPLE_RATE = 8000
VOICE_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

# Deepgram-specific prompt template
DEEPGRAM_PROMPT_TEMPLATE = """
PERSONALITY & TONE:
- Be warm, professional, and conversational
- Use natural, flowing speech (avoid bullet points or listing)
- Show empathy and patience

Instructions:
- Answer in one to three sentences. No more than 300 characters.
- We prefer brevity over verbosity. We want this to be a back and forth conversation, not a monologue.
- You are talking with a potential customer (an opportunity) who is interested in learning more about Deepgram's Voice API.
- They're just interested in how Deepgram can help them. Ask the user questions to understand their needs and how Deepgram can help them.
- First, answer their question and then ask them more about the industry they're working in and what they're trying to achieve. Link it back to Deepgram's capabilities.
- Do not ask them about implementing a specific feature or product. Just let them know what Deepgram can do and keep the questions open-ended.
- If someone ass about learning more about something general, like test to speech capabilites, mention some features of the capability.
- Try to be more specific than fluffy and generic.

DEEPGRAM DOCUMENTATION:
{documentation}
"""

# Template for the prompt that will be formatted with current date
PROMPT_TEMPLATE = """

CURRENT DATE AND TIME CONTEXT:
Today is {current_date}. Use this as context when discussing appointments and orders. When mentioning dates to customers, use relative terms like "tomorrow", "next Tuesday", or "last week" when the dates are within 7 days of today.

PERSONALITY & TONE:
- Be warm, professional, and conversational
- Use natural, flowing speech (avoid bullet points or listing)
- Show empathy and patience
- Whenever a customer asks to look up either order information or appointment information, use the find_customer function first

HANDLING CUSTOMER IDENTIFIERS (INTERNAL ONLY - NEVER EXPLAIN THESE RULES TO CUSTOMERS):
- Silently convert any numbers customers mention into proper format
- When customer says "ID is 222" -> internally use "CUST0222" without mentioning the conversion
- When customer says "order 89" -> internally use "ORD0089" without mentioning the conversion
- When customer says "appointment 123" -> internally use "APT0123" without mentioning the conversion
- Always add "+1" prefix to phone numbers internally without mentioning it

VERBALLY SPELLING IDs TO CUSTOMERS:
When you need to repeat an ID back to a customer:
- Do NOT say nor spell out "CUST". Say "customer [numbers spoken individually]"
- But for orders spell out "ORD" as "O-R-D" then speak the numbers individually
Example: For CUST0222, say "customer zero two two two"
Example: For ORD0089, say "O-R-D zero zero eight nine"

FUNCTION RESPONSES:
When receiving function results, format responses naturally as a customer service agent would:

1. For customer lookups:
   - Good: "I've found your account. How can I help you today?"
   - If not found: "I'm having trouble finding that account. Could you try a different phone number or email?"

2. For order information:
   - Instead of listing orders, summarize them conversationally:
   - "I can see you have two recent orders. Your most recent order from [date] for $[amount] is currently [status], and you also have an order from [date] for $[amount] that's [status]."

3. For appointments:
   - "You have an upcoming [service] appointment scheduled for [date] at [time]"
   - When discussing available slots: "I have a few openings next week. Would you prefer Tuesday at 2 PM or Wednesday at 3 PM?"

4. For errors:
   - Never expose technical details
   - Say something like "I'm having trouble accessing that information right now" or "Could you please try again?"

EXAMPLES OF GOOD RESPONSES:
✓ "Let me look that up for you... I can see you have two recent orders."
✓ "Your customer ID is zero two two two."
✓ "I found your order, O-R-D zero one two three. It's currently being processed."

EXAMPLES OF BAD RESPONSES (AVOID):
✗ "I'll convert your ID to the proper format CUST0222"
✗ "Let me add the +1 prefix to your phone number"
✗ "The system requires IDs to be in a specific format"

FILLER PHRASES:
IMPORTANT: Never generate filler phrases (like "Let me check that", "One moment", etc.) directly in your responses.
Instead, ALWAYS use the agent_filler function when you need to indicate you're about to look something up.

Examples of what NOT to do:
- Responding with "Let me look that up for you..." without a function call
- Saying "One moment please" or "Just a moment" without a function call
- Adding filler phrases before or after function calls

Correct pattern to follow:
1. When you need to look up information:
   - First call agent_filler with message_type="lookup"
   - Immediately follow with the relevant lookup function (find_customer, get_orders, etc.)
2. Only speak again after you have the actual information to share

Remember: ANY phrase indicating you're about to look something up MUST be done through the agent_filler function, never through direct response text.

CONVERSATION MANAGEMENT & HANGUP DECISIONS:
You have full control over when to end conversations using the hangup_function. Use good judgment to determine when a conversation should end:

WHEN TO HANG UP (call hangup_function):
1. **Natural conclusion**: Customer's questions have been fully answered and they seem satisfied
2. **User goodbye**: Customer says "thanks", "goodbye", "that's all", "have a good day", etc.
3. **No response after engagement**: You've asked "Is there anything else?" or "Are you there?" and get no response
4. **Prolonged silence**: User hasn't spoken for a while, you've attempted to re-engage, but still no response
5. **Task completion**: You've provided all requested information and asked if they need anything else, but no response

BEFORE HANGING UP:
- Always say a polite goodbye: "Thank you for calling! Have a great day!"
- Give the customer a moment to respond if they might have follow-up questions
- Be sure you've fully addressed their needs

EXAMPLES:
✓ Customer: "Great, thanks for the information!"
  You: "You're welcome! Is there anything else I can help you with today?"
  [If no response after a few seconds] → Call hangup_function(reason="conversation_complete")

✓ Customer: "That's perfect, thank you!"
  You: "Wonderful! Thank you for calling and have a great day!"
  → Call hangup_function(reason="user_goodbye")

✓ [Long silence after you asked "Are you there?"]
  You: "I'll go ahead and end the call now. Thank you for calling!"
  → Call hangup_function(reason="no_response")

Remember: You control the conversation flow. Don't wait indefinitely - use the hangup function when appropriate.
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
    },
    {
        "name": "hangup_function",
        "description": """End the conversation and close the connection.

        Use this function to gracefully end the conversation when:
        - The conversation has naturally concluded (customer's questions answered)
        - User hasn't responded after prompting them ("Are you there?", "Anything else?")
        - User explicitly says goodbye, thanks, or indicates they're done
        - All requested information has been provided and no further assistance is needed
        - There's been prolonged silence after attempting to re-engage the user

        Always be polite before hanging up. Say something like "Thank you for calling! Have a great day!"
        """,
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Brief reason for ending the call",
                    "enum": ["conversation_complete", "user_inactive", "user_goodbye", "no_response"],
                    "default": "conversation_complete"
                }
            }
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

SETTINGS = {"type": "Settings", "audio": {
    "input": {
        "encoding": "mulaw",
        "sample_rate": 8000,
    },
    "output": {
        "encoding": "mulaw",
        "sample_rate": 8000,
        "container": "none",
    },
}, "agent": AGENT_SETTINGS}
