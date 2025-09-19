import pytest
from app.services.agent_chat_service import AgentChatService
from app.utils.agent_config_builder import AgentConfigBuilder

class DummyAgent:
    id = "agent1"
    tenant_id = "tenant1"
    tools = ["search_collection"]
    provider = "test"
    model = "test-model"

@pytest.fixture
def dummy_context():
    return {
        "conversations": [
            {"id": "c1", "caller_phone": "+123", "started_at": "2023-01-01T10:00:00", "summary": "Test summary."}
        ],
        "messages": [
            {"role": "user", "content": "Hello!", "created_at": "2023-01-01T10:01:00"}
        ],
        "total_conversations": 1,
        "total_messages": 1,
    }

def test_build_agent_context_prompt_includes_collections(dummy_context):
    service = AgentChatService.__new__(AgentChatService)
    collections = [
        {"collection_name": "Docs", "description": "Documentation.", "notes": "Use for reference."}
    ]
    prompt = service._build_agent_context_prompt(
        query="What is the policy?",
        context_data=dummy_context,
        system_prompt="System base prompt.",
        collections=collections
    )
    assert "You have been provided with 1 collections" in prompt
    assert "Docs" in prompt
    assert "Documentation." in prompt
    assert "CURRENT QUERY: What is the policy?" in prompt
    assert "RECENT CONVERSATIONS" in prompt
    assert "RECENT MESSAGES" in prompt

