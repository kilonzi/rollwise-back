"""
Voice choices configuration for ElevenLabs integration.

Contains predefined voice options that can be selected for agents.
"""

ELEVEN_LABS_VOICES = [
    {
        "name": "Tiffiany",
        "id": "6aDn1KB0hjpdcocrUkmq",
        "gender": "female"
    },
    {
        "name": "Jessica",
        "id": "g6xIsTj2HwM6VR4iXFCw",
        "gender": "female"
    },
    {
        "name": "Cassidy",
        "id": "56AoDkrOh6qfVPDXZ7Pt",
        "gender": "female"
    },
    {
        "name": "Jason",
        "id": "UgBBYS2sOqTuMpoF3BR0",
        "gender": "male"
    },
    {
        "name": "Joe",
        "id": "gs0tAILXbY5DNrJrsM6F",
        "gender": "male"
    },
    {
        "name": "Jojo",
        "id": "c6SfcYrb2t09NHXiT80T",
        "gender": "male"
    }
]

DEEPGRAM_VOICES = [
    {
        "name": "Thalia",
        "id": "aura-2-thalia-en",
        "gender": "female"
    },
    {
        "name": "Andromeda",
        "id": "aura-2-andromeda-en",
        "gender": "female"
    },
    {
        "name": "Orion",
        "id": "aura-2-orion-en",
        "gender": "male"
    },
    {
        "name": "Helios",
        "id": "aura-2-helios-en",
        "gender": "male"
    }
]

def get_voice_choices() -> Dict[str, List[Dict[str, str]]]:
    """
    Get all available voice choices for agents.

    Returns:
        Dict with ElevenLabs and Deepgram voice options
    """
    return {
        "eleven_labs": ELEVEN_LABS_VOICES,
        "deepgram": DEEPGRAM_VOICES
    }

def get_voice_by_id(voice_id: str, provider: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Get voice information by ID.

    Args:
        voice_id: The voice ID to search for
        provider: Optional provider filter ("eleven_labs" or "deepgram")

    Returns:
        Voice dict if found, None otherwise
    """
    voices_to_search = []

    if provider == "eleven_labs":
        voices_to_search = ELEVEN_LABS_VOICES
    elif provider == "deepgram":
        voices_to_search = DEEPGRAM_VOICES
    else:
        voices_to_search = ELEVEN_LABS_VOICES + DEEPGRAM_VOICES

    for voice in voices_to_search:
        if voice["id"] == voice_id:
            return voice

    return None

def validate_voice_id(voice_id: str, provider: str):
    """
    Validate if a voice ID is valid for the given provider.

    Args:
        voice_id: The voice ID to validate
        provider: The voice provider ("eleven_labs" or "deepgram")

    Returns:
        bool: True if valid, False otherwise
    """
    if not voice_id:
        return False

    voice = get_voice_by_id(voice_id, provider)
    return voice is not None