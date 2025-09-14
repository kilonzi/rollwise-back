import json
from typing import Dict, Any

import websockets

from app.config.settings import settings


class DeepgramService:
    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_config = agent_config
        self.connection = None

    @staticmethod
    def connect():
        """Create connection to Deepgram Agent API"""
        if not settings.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is required")

        return websockets.connect(
            "wss://agent.deepgram.com/v1/agent/converse",
            subprotocols=["token", settings.DEEPGRAM_API_KEY],
        )

    async def send_config(self, websocket):
        """Send agent configuration to Deepgram"""
        await websocket.send(json.dumps(self.agent_config))

    async def send_audio(self, websocket, audio_data: bytes):
        """Send audio data to Deepgram"""
        await websocket.send(audio_data)

    async def send_tool_result(self, websocket, tool_name: str, result: Dict[str, Any]):
        """Send tool execution result back to Deepgram"""
        tool_response = {
            "type": "ToolResult",
            "tool": {"name": tool_name, "result": result},
        }
        await websocket.send(json.dumps(tool_response))

    @staticmethod
    def parse_message(message: str) -> Dict[str, Any]:
        """Parse incoming message from Deepgram"""
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            return {"type": "error", "message": "Invalid JSON"}
