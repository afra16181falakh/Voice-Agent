import asyncio
import json
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
from app.core.interfaces.gateway import ISpeechGateway
from app.core.models import ConversationState

logger = structlog.get_logger(__name__)

class SpeechGateway(ISpeechGateway):
    """
    Handles WebSocket connections between client browsers and internal 
    conversation services. Pushes raw user audio bytes down to the Conversation 
    Manager, and sends back generated assistant audio chunks and state events.
    """

    def __init__(self, session_manager, conversation_manager):
        self.session_manager = session_manager
        self.conversation_manager = conversation_manager

    async def handle_connection(self, websocket: WebSocket, session_id: str) -> None:
        """
        Runs the async receive loop for an active user WebSocket session, 
        forwarding events to the ConversationManager.
        """
        # Register the websocket connection
        await self.session_manager.register_connection(session_id, websocket)
        
        # Initialize conversation session in manager
        try:
            await self.conversation_manager.initialize_session(session_id)
        except Exception as e:
            logger.error("failed_initializing_conversation_session", error=str(e), session_id=session_id)
            await websocket.close(code=4000, reason="Failed to initialize conversation session")
            return

        logger.info("gateway_connection_loop_started", session_id=session_id)

        try:
            while True:
                data = await websocket.receive()

                # Starlette can deliver a disconnect as a plain message here
                # rather than always raising WebSocketDisconnect. Looping back
                # into receive() after that raises "Cannot call receive once a
                # disconnect message has been received" — break cleanly instead.
                if data.get("type") == "websocket.disconnect":
                    logger.info("gateway_client_disconnected", session_id=session_id)
                    break

                # Check message type
                if "bytes" in data:
                    audio_chunk = data["bytes"]
                    # Forward raw user PCM16 audio to the Conversation Manager
                    await self.conversation_manager.handle_user_audio(session_id, audio_chunk)
                    
                elif "text" in data:
                    text_msg = data["text"]
                    try:
                        payload = json.loads(text_msg)
                        if payload.get("type") == "text_input":
                            user_text = payload.get("text", "")
                            # Forward text to Gemini — conversation.py handles
                            # memory recording and context injection internally.
                            await self.conversation_manager.handle_user_text(session_id, user_text)
                            # Echo user text back to client chatbox
                            if user_text:
                                await self.send_user_transcript(session_id, user_text)
                    except json.JSONDecodeError:
                        logger.warning("received_non_json_text_frame", text=text_msg, session_id=session_id)
                        
        except WebSocketDisconnect:
            logger.info("gateway_client_disconnected", session_id=session_id)
        except Exception as e:
            logger.error("gateway_session_error", error=str(e), session_id=session_id)
        finally:
            # Clean up session resources
            await self.conversation_manager.terminate_session(session_id)
            await self.session_manager.close_session(session_id)
            logger.info("gateway_connection_loop_terminated", session_id=session_id)

    async def send_audio_chunk(self, session_id: str, chunk: bytes) -> None:
        """Sends a raw binary audio chunk to the client WebSocket."""
        websocket: Optional[WebSocket] = await self.session_manager.get_connection(session_id)
        if websocket:
            try:
                await websocket.send_bytes(chunk)
            except Exception as e:
                logger.error("failed_sending_audio_bytes_to_client", error=str(e), session_id=session_id)

    async def send_transcript_chunk(self, session_id: str, text: str, is_final: bool) -> None:
        """Sends real-time transcript updates to the client WebSocket (no-op since conversation log is removed)."""
        pass

    async def send_user_transcript(self, session_id: str, text: str) -> None:
        """Helper to send the finalized user transcript back to client (no-op since conversation log is removed)."""
        pass

    async def send_interruption_signal(self, session_id: str) -> None:
        """Sends an explicit interruption/barge-in signal to the client."""
        websocket: Optional[WebSocket] = await self.session_manager.get_connection(session_id)
        if websocket:
            try:
                payload = {
                    "type": "state_transition",
                    "state": "interrupted"
                }
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.error("failed_sending_interruption_to_client", error=str(e), session_id=session_id)

    async def send_turn_failed(self, session_id: str) -> None:
        """Notifies the client that a turn stalled with no response (watchdog-triggered)."""
        websocket: Optional[WebSocket] = await self.session_manager.get_connection(session_id)
        if websocket:
            try:
                payload = {"type": "turn_failed"}
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.error("failed_sending_turn_failed_to_client", error=str(e), session_id=session_id)

    async def send_retry_status(self, session_id: str, attempt: int, max_retries: int) -> None:
        """Notifies the client that the Gemini receive loop is reconnecting."""
        websocket: Optional[WebSocket] = await self.session_manager.get_connection(session_id)
        if websocket:
            try:
                payload = {
                    "type": "reconnecting",
                    "attempt": attempt,
                    "max_retries": max_retries,
                }
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.error("failed_sending_retry_status_to_client", error=str(e), session_id=session_id)

    async def send_state_transition(self, session_id: str, state: ConversationState) -> None:
        """Broadcasts active ConversationState to the client for UI animations."""
        websocket: Optional[WebSocket] = await self.session_manager.get_connection(session_id)
        if websocket:
            try:
                payload = {
                    "type": "state_transition",
                    "state": state.value
                }
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.error("failed_sending_state_transition_to_client", error=str(e), session_id=session_id)

    async def terminate_session(self, session_id: str) -> None:
        """Explicitly closes client WebSocket."""
        websocket: Optional[WebSocket] = await self.session_manager.get_connection(session_id)
        if websocket:
            try:
                await websocket.close(code=1000, reason="Session ended by server request")
            except Exception as e:
                logger.debug("failed_closing_client_websocket_on_termination", error=str(e), session_id=session_id)
