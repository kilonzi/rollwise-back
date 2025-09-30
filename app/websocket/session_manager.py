"""
WebSocket session management for agent voice calls.

This module provides clean separation of concerns for managing WebSocket connections
between Twilio and Deepgram for voice-based AI agent conversations.
"""

import asyncio
import base64
import json
from enum import Enum
from typing import Optional, List, Dict, Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models import Agent, Conversation
from app.services.agent_service import AgentService
from app.services.conversation_service import ConversationService
from app.services.deepgram_service import DeepgramService
from app.utils.logging_config import app_logger as logger


class SessionState(Enum):
    """WebSocket session states for tracking lifecycle"""

    INITIALIZING = "initializing"
    CONNECTING = "connecting"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


class WebSocketSession:
    """Manages the complete WebSocket session lifecycle"""

    def __init__(
        self,
        websocket: WebSocket,
        agent_id: str,
        conversation_id: str,
        db_session: Session,
    ):
        self.websocket = websocket
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.db_session = db_session
        self.state = SessionState.INITIALIZING

        # Services
        self.agent_service = AgentService(db_session)
        self.conversation_service = ConversationService(db_session)

        # Session data
        self.agent: Optional[Agent] = None
        self.conversation: Optional[Conversation] = None
        self.agent_config: Optional[Dict[str, Any]] = None

        # Components
        self.deepgram_handler: Optional[DeepgramHandler] = None
        self.audio_processor: Optional[AudioProcessor] = None
        self.twilio_handler: Optional[TwilioHandler] = None

        # Tasks
        self.tasks: List[asyncio.Task] = []
        self.cleanup_completed = False

        logger.info(
            f"[SESSION] Initialized for agent {agent_id}, conversation {conversation_id}"
        )

    async def setup(self) -> bool:
        """Setup and validate all session components"""
        try:
            logger.info(f"[SESSION] Setting up session for agent {self.agent_id}")

            # 1. Validate agent
            self.agent = self.agent_service.get_agent_by_id(self.agent_id)
            if not self.agent:
                logger.error(f"[SESSION] Agent {self.agent_id} not found or inactive")
                await self.websocket.close(code=1008, reason="Business not available")
                return False

            logger.info(
                f"[SESSION] Agent validated: {self.agent.name} ({self.agent.id})"
            )

            # 2. Validate conversation
            self.conversation = self.conversation_service.get_conversation(
                self.conversation_id
            )
            if not self.conversation:
                logger.error(f"[SESSION] Conversation {self.conversation_id} not found")
                await self.websocket.close(code=1011, reason="Conversation not found")
                return False

            logger.info(f"[SESSION] Using conversation: {self.conversation.id}")

            # 3. Build agent configuration
            self.agent_config = self.agent_service.build_agent_config(
                agent=self.agent,
                phone_number=self.conversation.caller_phone,
                conversation_id=self.conversation.id,
            )

            if not self.agent_config:
                logger.error("[SESSION] Failed to build agent configuration")
                await self.websocket.close(
                    code=1011, reason="Agent configuration error"
                )
                return False

            function_count = len(
                self.agent_config.get("agent", {}).get("think", {}).get("functions", [])
            )
            logger.info(f"[SESSION] Built agent config with {function_count} functions")

            # 4. Initialize components
            self.audio_processor = AudioProcessor()
            self.deepgram_handler = DeepgramHandler(
                self.agent_config, self.conversation, self.db_session
            )
            self.twilio_handler = TwilioHandler(self.websocket, self.audio_processor)

            self.state = SessionState.CONNECTING
            logger.info("[SESSION] Setup completed successfully")
            return True

        except Exception as e:
            logger.exception(f"[SESSION] Setup failed: {e}")
            self.state = SessionState.ERROR
            return False

    async def start_processing(self) -> bool:
        """Start all processing components and handle the session"""
        try:
            logger.info("[SESSION] Starting processing components")

            # Connect to Deepgram first
            if not await self.deepgram_handler.connect():
                logger.error("[SESSION] Failed to connect to Deepgram")
                return False

            # Pass TwilioHandler reference to DeepgramHandler for audio routing
            self.deepgram_handler.twilio_handler = self.twilio_handler

            # Start all processing tasks
            self.tasks = [
                asyncio.create_task(
                    self.deepgram_handler.receive_messages(self.audio_processor)
                ),
                asyncio.create_task(self.twilio_handler.handle_twilio_messages()),
                asyncio.create_task(
                    self.audio_processor.send_audio_to_deepgram(
                        self.deepgram_handler.deepgram_ws
                    )
                ),
            ]

            self.state = SessionState.ACTIVE
            logger.info("[SESSION] All components started, session is active")

            # Wait for all tasks to complete or fail
            await asyncio.gather(*self.tasks, return_exceptions=True)

            return True

        except Exception as e:
            logger.exception(f"[SESSION] Processing failed: {e}")
            self.state = SessionState.ERROR
            return False
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up all resources in proper order"""
        if self.cleanup_completed:
            return

        self.cleanup_completed = True
        self.state = SessionState.CLOSING
        logger.info("[SESSION] Starting cleanup...")

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Cleanup components in reverse order
        if self.deepgram_handler:
            await self.deepgram_handler.cleanup()

        if self.audio_processor:
            await self.audio_processor.cleanup()

        if self.twilio_handler:
            await self.twilio_handler.cleanup()

        # End conversation
        try:
            if self.conversation:
                await self.conversation_service.end_conversation(self.conversation.id)
                logger.info(f"[SESSION] Ended conversation: {self.conversation.id}")
        except Exception as cleanup_error:
            logger.exception(f"[SESSION] Error ending conversation: {cleanup_error}")

        # Close WebSocket
        try:
            if hasattr(self.websocket, "client_state") and not getattr(
                self.websocket.client_state, "DISCONNECTED", False
            ):
                await self.websocket.close()
                logger.info("[SESSION] WebSocket closed")
        except Exception as ws_error:
            logger.exception(f"[SESSION] Error closing WebSocket: {ws_error}")

        self.state = SessionState.CLOSED
        logger.info("[SESSION] Cleanup completed")


class AudioProcessor:
    """Handles audio streaming and buffering between Twilio and Deepgram"""

    def __init__(self):
        self.audio_queue = asyncio.Queue()
        self.stream_sid_queue = asyncio.Queue()
        self.user_audio_buffer: List[bytes] = []
        self.agent_audio_buffer: List[bytes] = []
        self.is_running = False

        logger.info("[AUDIO] Audio processor initialized")

    async def queue_audio_chunk(self, audio_chunk: bytes):
        """Queue an audio chunk for processing"""
        if audio_chunk:
            await self.audio_queue.put(audio_chunk)
            self.user_audio_buffer.append(audio_chunk)

    async def queue_stream_sid(self, stream_sid: str):
        """Queue a stream SID for audio responses"""
        await self.stream_sid_queue.put(stream_sid)

    async def get_stream_sid(self) -> str:
        """Get the current stream SID"""
        return await self.stream_sid_queue.get()

    def put_stream_sid_back(self, stream_sid: str):
        """Put stream SID back for reuse"""
        self.stream_sid_queue.put_nowait(stream_sid)

    async def send_audio_to_deepgram(self, deepgram_ws):
        """Send queued audio to Deepgram with proper error handling"""
        self.is_running = True
        logger.info("[AUDIO] Started audio sender")

        try:
            # Wait before starting to ensure Deepgram is ready
            await asyncio.sleep(0.2)

            while self.is_running:
                try:
                    audio_chunk = await self.audio_queue.get()
                    if audio_chunk is None:  # Stop signal
                        logger.info("[AUDIO] Received stop signal")
                        break

                    # Check connection state before sending with detailed logging
                    try:
                        current_state = deepgram_ws.state.name
                        if current_state in ["CLOSED", "CLOSING"]:
                            close_code = getattr(deepgram_ws, "close_code", "unknown")
                            close_reason = getattr(
                                deepgram_ws, "close_reason", "unknown"
                            )
                            logger.warning(
                                f"[AUDIO] Deepgram connection {current_state} - Code: {close_code}, Reason: {close_reason}"
                            )
                            break
                        else:
                            logger.debug(
                                f"[AUDIO] Connection state OK: {current_state}"
                            )
                    except AttributeError as attr_error:
                        logger.debug(
                            f"[AUDIO] Could not check connection state: {attr_error}"
                        )
                        pass

                    await deepgram_ws.send(audio_chunk)

                except asyncio.CancelledError:
                    logger.info("[AUDIO] Audio sender cancelled")
                    break
                except Exception as e:
                    logger.exception(f"[AUDIO] Error sending audio chunk: {e}")
                    continue

        except Exception as e:
            logger.exception(f"[AUDIO] Audio sender error: {e}")
        finally:
            self.is_running = False
            logger.info("[AUDIO] Audio sender stopped")

    async def stop_audio_sender(self):
        """Signal the audio sender to stop"""
        self.is_running = False
        await self.audio_queue.put(None)

    async def cleanup(self):
        """Clean up audio processor resources"""
        logger.info("[AUDIO] Cleaning up audio processor")
        await self.stop_audio_sender()
        self.user_audio_buffer.clear()
        self.agent_audio_buffer.clear()


class DeepgramHandler:
    """Handles Deepgram WebSocket connection and message processing"""

    def __init__(
        self,
        agent_config: Dict[str, Any],
        conversation: Conversation,
        db_session: Session,
    ):
        self.agent_config = agent_config
        self.conversation = conversation
        self.db_session = db_session
        self.deepgram_service = DeepgramService(agent_config)
        self.deepgram_ws = None
        self.is_connected = False
        self.connection_manager = None
        self.twilio_handler = None  # Reference to TwilioHandler

        logger.info("[DEEPGRAM] Handler initialized")

    async def connect(self) -> bool:
        """Connect to Deepgram and send configuration"""
        try:
            logger.info("[DEEPGRAM] Connecting to Deepgram Agent API")

            # Print the agent config being sent for debugging
            logger.info(
                f"[DEEPGRAM] Agent config: {json.dumps(self.agent_config, indent=2)}"
            )

            # Don't use context manager here - we need to keep the connection open
            self.connection_manager = self.deepgram_service.connect()
            self.deepgram_ws = await self.connection_manager.__aenter__()

            logger.info(
                f"[DEEPGRAM] Connected to Deepgram - Connection state: {self.deepgram_ws.state}"
            )
            logger.info(
                f"[DEEPGRAM] Connection details - ID: {getattr(self.deepgram_ws, 'id', 'N/A')}"
            )

            # Send configuration and wait for processing
            await self.deepgram_service.send_config(self.deepgram_ws)
            logger.info("[DEEPGRAM] Configuration sent successfully")

            # Check connection state after config
            logger.info(
                f"[DEEPGRAM] Connection state after config: {self.deepgram_ws.state}"
            )

            # Wait for Deepgram to process the configuration
            await asyncio.sleep(0.5)

            # Check connection state after wait
            logger.info(
                f"[DEEPGRAM] Connection state after wait: {self.deepgram_ws.state}"
            )

            self.is_connected = True
            return True

        except Exception as e:
            logger.exception(f"[DEEPGRAM] Connection failed: {e}")
            self.is_connected = False
            if self.connection_manager:
                try:
                    await self.connection_manager.__aexit__(None, None, None)
                except Exception:
                    pass
            return False

    async def receive_messages(self, audio_processor: AudioProcessor):
        """Receive and process messages from Deepgram"""
        logger.info("[DEEPGRAM] Started message receiver")

        try:
            async for message in self.deepgram_ws:
                try:
                    if isinstance(message, str):
                        await self._handle_text_message(message)
                    elif isinstance(message, bytes):
                        await self._handle_audio_message(message, audio_processor)

                except Exception as msg_error:
                    logger.exception(
                        f"[DEEPGRAM] Error processing message: {msg_error}"
                    )
                    continue

        except asyncio.CancelledError:
            logger.info("[DEEPGRAM] Message receiver cancelled")
        except ConnectionClosedError as e:
            # Check if this was an intentional hangup (close code 1000 = normal closure)
            if e.code == 1000:
                logger.info("[DEEPGRAM] Connection closed normally (hangup)")
            elif e.code == 1006:
                logger.info(
                    "[DEEPGRAM] Connection closed by hangup function - this is expected"
                )
            else:
                logger.warning(
                    f"[DEEPGRAM] Connection closed unexpectedly: {e.code} - {e.reason}"
                )
        except Exception as e:
            logger.exception(f"[DEEPGRAM] Message receiver error: {e}")
        finally:
            logger.info("[DEEPGRAM] Message receiver stopped")

    async def _handle_text_message(self, message: str):
        """Handle text messages from Deepgram"""
        try:
            data = json.loads(message)
            event_type = data.get("type")

            logger.debug(f"[DEEPGRAM] Received {event_type} message")

            if event_type == "ConversationText":
                await self._handle_conversation_text(data)
            elif event_type == "FunctionCallRequest":
                await self._handle_function_call_request(data)
            else:
                await self._handle_other_event(data)

        except json.JSONDecodeError:
            logger.error(f"[DEEPGRAM] Invalid JSON received: {message[:100]}...")
        except Exception as e:
            logger.exception(f"[DEEPGRAM] Error handling text message: {e}")

    async def _handle_audio_message(
        self, message: bytes, audio_processor: AudioProcessor
    ):
        """Handle audio messages from Deepgram"""
        try:
            # This is agent speech audio - we need to send it back to Twilio
            audio_processor.agent_audio_buffer.append(message)
            logger.debug(f"[DEEPGRAM] Received {len(message)} bytes of agent audio")

            # Send audio directly to Twilio via the TwilioHandler
            if self.twilio_handler:
                await self.twilio_handler.send_audio_to_twilio(message)
                logger.debug(f"[DEEPGRAM] Sent {len(message)} bytes to Twilio")
            else:
                logger.warning(
                    "[DEEPGRAM] No TwilioHandler available for audio routing"
                )

        except Exception as e:
            logger.exception(f"[DEEPGRAM] Error handling audio message: {e}")

    async def _handle_conversation_text(self, data: Dict[str, Any]):
        """Handle conversation text from Deepgram"""
        # Import here to avoid circular imports
        from app.api.routers.communication import handle_conversation_text

        await handle_conversation_text(
            data,
            self.conversation,
            self.db_session,
            [],
            [],  # Audio buffers will be handled separately
        )

    async def _handle_function_call_request(self, data: Dict[str, Any]):
        """Handle function call requests from Deepgram"""
        # Import here to avoid circular imports
        from app.api.routers.communication import handle_function_call_request

        await handle_function_call_request(
            data, self.deepgram_ws, self.conversation, self.db_session
        )

    async def _handle_other_event(self, data: Dict[str, Any]):
        """Handle other events from Deepgram"""
        event_type = data.get("type")

        if event_type == "UserStartedSpeaking":
            logger.info("[DEEPGRAM] User started speaking")
        elif event_type == "UserEndedSpeaking":
            logger.info("[DEEPGRAM] User stopped speaking")
        elif event_type == "SpeechStarted":
            logger.info("[DEEPGRAM] Agent started speaking")
        elif event_type == "AgentEndedSpeaking":
            logger.info("[DEEPGRAM] Agent stopped speaking")
        else:
            logger.debug(f"[DEEPGRAM] Unhandled event type: {event_type}")

    async def cleanup(self):
        """Clean up Deepgram connection"""
        logger.info("[DEEPGRAM] Cleaning up Deepgram handler")
        self.is_connected = False

        # Properly close the connection manager
        if self.connection_manager:
            try:
                await self.connection_manager.__aexit__(None, None, None)
                logger.info("[DEEPGRAM] Connection manager closed")
            except Exception as e:
                logger.exception(f"[DEEPGRAM] Error closing connection: {e}")
            finally:
                self.connection_manager = None
                self.deepgram_ws = None


class TwilioHandler:
    """Handles Twilio WebSocket messages and responses"""

    def __init__(self, websocket: WebSocket, audio_processor: AudioProcessor):
        self.websocket = websocket
        self.audio_processor = audio_processor
        self.is_running = False

        logger.info("[TWILIO] Handler initialized")

    async def handle_twilio_messages(self):
        """Handle incoming messages from Twilio WebSocket"""
        self.is_running = True
        logger.info("[TWILIO] Started message handler")

        try:
            while self.is_running:
                try:
                    message = await self.websocket.receive_text()
                    data = json.loads(message)

                    event_type = data.get("event")

                    if event_type == "start":
                        await self._handle_start_event(data)
                    elif event_type == "media":
                        await self._handle_media_event(data)
                    elif event_type == "stop":
                        await self._handle_stop_event(data)
                    else:
                        logger.debug(f"[TWILIO] Unhandled event type: {event_type}")

                except json.JSONDecodeError:
                    logger.warning("[TWILIO] Invalid JSON received from Twilio")
                    continue
                except Exception as msg_error:
                    logger.exception(f"[TWILIO] Error processing message: {msg_error}")
                    continue

        except asyncio.CancelledError:
            logger.info("[TWILIO] Message handler cancelled")
        except Exception as e:
            logger.exception(f"[TWILIO] Message handler error: {e}")
        finally:
            self.is_running = False
            logger.info("[TWILIO] Message handler stopped")

    async def _handle_start_event(self, data: Dict[str, Any]):
        """Handle call start event"""
        stream_sid = data["start"]["streamSid"]
        await self.audio_processor.queue_stream_sid(stream_sid)
        logger.info(f"[TWILIO] Call started: {stream_sid}")

    async def _handle_media_event(self, data: Dict[str, Any]):
        """Handle media (audio) event"""
        media = data["media"]
        audio_chunk = base64.b64decode(media["payload"])
        await self.audio_processor.queue_audio_chunk(audio_chunk)

    async def _handle_stop_event(self, data: Dict[str, Any]):
        """Handle call stop event"""
        logger.info("[TWILIO] Call stop event received")
        self.is_running = False
        await self.audio_processor.stop_audio_sender()

    async def send_audio_to_twilio(self, audio_data: bytes):
        """Send audio back to Twilio with proper connection state checking"""
        try:
            # Check if handler is still running and websocket is available
            if not self.is_running:
                logger.debug("[TWILIO] Handler stopped, skipping audio send")
                return

            # Check websocket connection state using the client_state attribute
            # In older FastAPI versions, client_state is an integer or enum value
            try:
                # Try to access client_state - if it fails, websocket is likely closed
                client_state = getattr(self.websocket, "client_state", None)
                if client_state is None:
                    logger.debug(
                        "[TWILIO] WebSocket client_state not available, skipping audio send"
                    )
                    return

                # Check if websocket is in a disconnected state
                # Different FastAPI versions use different representations
                if hasattr(client_state, "name"):
                    state_name = client_state.name
                    if state_name in ["DISCONNECTED", "CLOSED"]:
                        logger.debug(
                            f"[TWILIO] WebSocket {state_name}, skipping audio send"
                        )
                        return
                elif str(client_state) in ["3", "DISCONNECTED", "CLOSED"]:
                    logger.debug(
                        f"[TWILIO] WebSocket disconnected ({client_state}), skipping audio send"
                    )
                    return

            except AttributeError:
                # If we can't check state, try to send anyway and handle errors
                logger.debug(
                    "[TWILIO] Could not check WebSocket state, attempting send"
                )

            stream_sid = await self.audio_processor.get_stream_sid()
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

            media_message = {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": audio_b64},
            }

            self.audio_processor.put_stream_sid_back(stream_sid)

            # Send with additional error handling for closed connections
            await self.websocket.send_text(json.dumps(media_message))
            logger.debug(f"[TWILIO] Successfully sent {len(audio_data)} bytes of audio")

        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.info(
                    "[TWILIO] WebSocket closed by client/server, stopping audio transmission"
                )
                self.is_running = False  # Stop the handler to prevent further attempts
            else:
                logger.warning(f"[TWILIO] Runtime error sending audio: {e}")
        except ConnectionResetError:
            logger.info("[TWILIO] Connection reset by peer, call ended")
            self.is_running = False
        except Exception as e:
            logger.error(f"[TWILIO] Error sending audio: {e}")
            # Don't stop on other errors, just log them

    async def cleanup(self):
        """Clean up Twilio handler"""
        logger.info("[TWILIO] Cleaning up Twilio handler")
        self.is_running = False
