import asyncio
import structlog
from typing import Dict, Set, Callable, Awaitable
from app.core.models import ConversationState

logger = structlog.get_logger(__name__)

class InvalidStateTransition(Exception):
    def __init__(self, from_state: ConversationState, to_state: ConversationState):
        super().__init__(f"Cannot transition conversation from {from_state.value} to {to_state.value}")
        self.from_state = from_state
        self.to_state = to_state


class ConversationStateMachine:
    """
    Manages the conversational state of a session and broadcasts transitions
    to registered listeners.
    """

    # Define valid transition rules
    VALID_TRANSITIONS: Dict[ConversationState, Set[ConversationState]] = {
        ConversationState.IDLE: {
            ConversationState.LISTENING,
            ConversationState.THINKING,
            ConversationState.PROCESSING,
            ConversationState.ENDING
        },
        ConversationState.LISTENING: {
            ConversationState.PROCESSING,
            ConversationState.THINKING,
            ConversationState.SPEAKING,
            ConversationState.IDLE,
            ConversationState.INTERRUPTED,
            ConversationState.SILENCE
        },
        ConversationState.PROCESSING: {
            ConversationState.SPEAKING,
            ConversationState.IDLE,
            ConversationState.INTERRUPTED,
            ConversationState.SILENCE
        },
        ConversationState.THINKING: {
            ConversationState.SPEAKING,
            ConversationState.IDLE,
            ConversationState.INTERRUPTED
        },
        ConversationState.SPEAKING: {
            ConversationState.IDLE,
            ConversationState.LISTENING,
            ConversationState.INTERRUPTED,
            ConversationState.PROCESSING
        },
        ConversationState.INTERRUPTED: {
            ConversationState.LISTENING,
            ConversationState.SPEAKING,
            ConversationState.IDLE,
            ConversationState.PROCESSING
        },
        ConversationState.SILENCE: {
            ConversationState.LISTENING,
            ConversationState.IDLE,
            ConversationState.ENDING
        },
        ConversationState.ENDING: {
            ConversationState.IDLE
        }
    }

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.current_state = ConversationState.IDLE
        self._listeners: Set[Callable[[ConversationState, ConversationState], Awaitable[None]]] = set()
        self._lock = asyncio.Lock()

    def register_listener(self, callback: Callable[[ConversationState, ConversationState], Awaitable[None]]) -> None:
        """Registers an async callback to trigger on state transitions."""
        self._listeners.add(callback)

    def unregister_listener(self, callback: Callable[[ConversationState, ConversationState], Awaitable[None]]) -> None:
        """Unregisters an async transition callback."""
        self._listeners.discard(callback)

    async def transition_to(self, target_state: ConversationState) -> None:
        """
        Transitions the state machine to a target state, verifying safety and
        notifying subscribers.

        The lock is held only for the state mutation itself.  Listener tasks are
        created inside the lock (so they see the new state) but awaited *after*
        the lock is released.  This prevents incoming transition calls from piling
        up behind WebSocket I/O inside the listener while the lock is held.
        """
        async with self._lock:
            old_state = self.current_state
            if old_state == target_state:
                return

            allowed_targets = self.VALID_TRANSITIONS.get(old_state, set())
            if target_state not in allowed_targets:
                logger.warning(
                    "invalid_transition_attempted",
                    session_id=self.session_id,
                    from_state=old_state.value,
                    to_state=target_state.value
                )
                raise InvalidStateTransition(old_state, target_state)

            self.current_state = target_state
            logger.info(
                "state_transitioned",
                session_id=self.session_id,
                old_state=old_state.value,
                new_state=target_state.value
            )

            # Snapshot listeners while the lock is held, then release before
            # awaiting so subsequent transitions are never blocked by I/O.
            listener_snapshot = list(self._listeners)

        # ── Lock released ────────────────────────────────────────────────────
        # Fire all listener callbacks concurrently.  Failures are collected by
        # gather(return_exceptions=True) and logged individually so one bad
        # listener never silences the others.
        if listener_snapshot:
            tasks = [
                asyncio.create_task(listener(old_state, target_state))
                for listener in listener_snapshot
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(
                        "transition_listener_error",
                        error=str(result),
                        session_id=self.session_id,
                    )

    def get_state(self) -> ConversationState:
        """Returns the current state."""
        return self.current_state
