from abc import ABC, abstractmethod
from typing import Any

class ISpeechGateway(ABC):
    """
    Interface for handling connection gateways between clients (e.g. WebSocket connection)
    and the Conversation Manager.
    """

    @abstractmethod
    async def handle_connection(self, connection: Any, session_id: str) -> None:
        """Handles a client WebSocket session lifecycle."""
        pass

    @abstractmethod
    async def send_audio_chunk(self, session_id: str, chunk: bytes) -> None:
        """Sends an output audio chunk to the user client."""
        pass

    @abstractmethod
    async def send_transcript_chunk(self, session_id: str, text: str, is_final: bool) -> None:
        """Sends a real-time text transcript chunk to the user client."""
        pass

    @abstractmethod
    async def send_interruption_signal(self, session_id: str) -> None:
        """Informs the client client that they have interrupted the assistant."""
        pass

    @abstractmethod
    async def terminate_session(self, session_id: str) -> None:
        """Force closes the connection to the client client."""
        pass
