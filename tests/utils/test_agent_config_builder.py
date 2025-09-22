from app.utils.agent_config_builder import AgentConfigBuilder


def test_format_collections_prompt_empty():
    assert (
        AgentConfigBuilder.format_collections_prompt([]) == "No collections available."
    )


def test_format_collections_prompt_single():
    collections = [
        {
            "collection_name": "Policies",
            "description": "Company policies and procedures.",
            "notes": "Always follow the latest version.",
        }
    ]
    prompt = AgentConfigBuilder.format_collections_prompt(collections)
    assert (
        "1. Policies — Purpose: Company policies and procedures. Key rules: Always follow the latest version."
        in prompt
    )
    assert "You have been provided with 1 collections" in prompt


def test_format_collections_prompt_multiple():
    collections = [
        {
            "collection_name": "Policies",
            "description": "Company policies.",
            "notes": "Follow strictly.",
        },
        {
            "collection_name": "FAQs",
            "description": "Frequently asked questions.",
            "rules": "Be concise.",
        },
    ]
    prompt = AgentConfigBuilder.format_collections_prompt(collections)
    assert "1. Policies" in prompt and "2. FAQs" in prompt
    assert "Purpose: Company policies." in prompt
    assert "Key rules: Be concise." in prompt
    assert "You have been provided with 2 collections" in prompt
