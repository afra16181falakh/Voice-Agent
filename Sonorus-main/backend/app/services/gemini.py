import asyncio
import structlog
from typing import Callable, Awaitable, Optional

from google import genai
from google.genai import types

from app.config import settings
from app.core.interfaces.provider import IConversationProvider

logger = structlog.get_logger(__name__)

# ── Retry policy ────────────────────────────────────────────
_MAX_RETRIES = 3                    # maximum reconnection attempts
_RETRY_DELAYS = [1.0, 2.0, 4.0]    # seconds before attempt 2, 3, 4
# ────────────────────────────────────────────────────────────


class GeminiLiveProvider(IConversationProvider):
    """
    Wraps the Google GenAI async Live API for bidirectional speech streaming.
    Manages a persistent WebSocket session with Gemini and dispatches events
    (audio chunks, text transcripts, interruptions, turn completions) to
    registered callbacks.

    The receive loop is resilient: transient WebSocket errors trigger up to
    _MAX_RETRIES automatic reconnections with exponential back-off before
    giving up and notifying callers.
    """

    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini.api_key)
        self._session_ctx = None
        self._session = None
        self._receive_task: Optional[asyncio.Task] = None

        # Stored connection params so _reconnect() can re-open with identical config
        self._connect_session_id: Optional[str] = None
        self._connect_system_instruction: Optional[str] = None
        self._connect_voice_name: Optional[str] = None

        # Intentional-close sentinel — prevents retries during deliberate teardown
        self._is_closed: bool = False

        # Set right before force_reconnect() (watchdog / go_away) swaps the
        # session out from under the still-running receive loop. That loop
        # will notice its old session closing and independently attempt its
        # own retry-driven reconnect shortly after — this flag lets it
        # recognize that as an already-handled, expected echo rather than a
        # fresh unexpected failure, so it doesn't alarm the user with a
        # redundant "Reconnecting..." notification for something already fixed.
        self._external_reconnect_pending: bool = False

        # Registered event callbacks
        self._on_audio: Optional[Callable[[bytes], Awaitable[None]]] = None
        self._on_text: Optional[Callable[[str, bool], Awaitable[None]]] = None
        self._on_interruption: Optional[Callable[[], Awaitable[None]]] = None
        self._on_turn: Optional[Callable[[Optional[str]], Awaitable[None]]] = None
        self._on_retry: Optional[Callable[[int, int], Awaitable[None]]] = None
        # Fired when Gemini transcribes the user's own voice input
        self._on_user_transcript: Optional[Callable[[str], Awaitable[None]]] = None
        # Fired when Gemini sends a go_away frame (server-initiated disconnect warning)
        self._on_go_away: Optional[Callable[[str], Awaitable[None]]] = None

    # ──────────────────────────────────────────────────────────
    # Callback registration
    # ──────────────────────────────────────────────────────────

    def register_audio_handler(self, callback: Callable[[bytes], Awaitable[None]]) -> None:
        self._on_audio = callback

    def register_text_handler(self, callback: Callable[[str, bool], Awaitable[None]]) -> None:
        self._on_text = callback

    def register_interruption_handler(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._on_interruption = callback

    def register_turn_handler(self, callback: Callable[[Optional[str]], Awaitable[None]]) -> None:
        self._on_turn = callback

    def register_retry_handler(self, callback: Callable[[int, int], Awaitable[None]]) -> None:
        """Registers a callback fired on each reconnection attempt: (attempt, max_retries)."""
        self._on_retry = callback

    def register_user_transcript_handler(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Registers a callback fired when Gemini transcribes the user's voice input."""
        self._on_user_transcript = callback

    def register_go_away_handler(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Registers a callback fired when Gemini sends a go_away (server-initiated disconnect warning)."""
        self._on_go_away = callback

    # ──────────────────────────────────────────────────────────
    # Session lifecycle
    # ──────────────────────────────────────────────────────────

    async def start_session(
        self,
        session_id: str,
        system_instruction: str,
        voice_name: str,
    ) -> None:
        """Opens a Gemini Live WebSocket session and starts the resilient receive loop."""
        # Persist connection params for use by _reconnect()
        self._connect_session_id = session_id
        self._connect_system_instruction = system_instruction
        self._connect_voice_name = voice_name
        self._is_closed = False

        self._session_ctx = self._client.aio.live.connect(
            model=settings.gemini.live_model,
            config=self._build_config(system_instruction, voice_name),
        )
        self._session = await self._session_ctx.__aenter__()

        # Kick off background receive loop with automatic retry on transient failure
        self._receive_task = asyncio.create_task(
            self._receive_loop(session_id),
            name=f"gemini_receive_{session_id}"
        )
        logger.info("gemini_live_session_started", session_id=session_id, voice=voice_name)

    async def send_audio(self, audio_chunk: bytes) -> None:
        """Streams a raw PCM16 audio chunk to Gemini."""
        if not self._session:
            return
        # Guard: if the receive loop is dead and not being retried, skip the send
        if self._receive_task and self._receive_task.done():
            logger.warning(
                "gemini_send_audio_skipped_dead_loop",
                session_id=self._connect_session_id,
            )
            return
        try:
            # `audio=` (not the older `media=`) — newer Live API models (e.g.
            # gemini-3.1-flash-live-preview) reject `media=`'s wire format
            # with "realtime_input.media_chunks is deprecated. Use audio,
            # video, or text instead." on every single chunk. `audio=` maps
            # to the current, non-deprecated field and works on both old and
            # new model generations.
            await self._session.send_realtime_input(
                audio=types.Blob(data=audio_chunk, mime_type="audio/pcm;rate=16000")
            )
        except Exception as e:
            logger.error("gemini_send_audio_failed", error=str(e))

    async def send_text(self, text: str) -> None:
        """Sends a text turn to Gemini."""
        if not self._session:
            return
        if self._receive_task and self._receive_task.done():
            logger.warning(
                "gemini_send_text_skipped_dead_loop",
                session_id=self._connect_session_id,
            )
            return
        try:
            await self._session.send_client_content(
                turns=[types.Content(parts=[types.Part.from_text(text=text)], role="user")],
                turn_complete=True,
            )
        except Exception as e:
            logger.error("gemini_send_text_failed", error=str(e))

    async def send_context_nudge(self, nudge: str) -> None:
        """
        Injects a brief context-steering message as a model turn BEFORE the
        user's actual message. Gemini sees this as prior model output and uses
        it to calibrate its next response style.

        This is the mechanism used to apply strategy/emotion context since
        Gemini Live does not support mid-session system instruction updates.
        """
        if not self._session or not nudge:
            return
        if self._receive_task and self._receive_task.done():
            return
        try:
            await self._session.send_client_content(
                turns=[types.Content(parts=[types.Part.from_text(text=nudge)], role="model")],
                turn_complete=False,  # Not a full turn — just a context prefix
            )
        except Exception as e:
            # Non-fatal: if nudge fails, user's message still gets sent
            logger.warning("gemini_context_nudge_failed", error=str(e))

    async def update_system_instruction(self, instruction: str) -> None:
        """
        Gemini Live does not currently support mid-session system instruction updates.
        This is a no-op stub for interface compliance.
        """
        logger.debug("update_system_instruction_not_supported_in_live_api")

    async def close(self) -> None:
        """Cancels the receive loop and closes the Gemini session."""
        # Set closed flag FIRST so the retry loop does not attempt reconnection
        # after the task is cancelled.
        self._is_closed = True

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                # google-genai SDK may raise AttributeError on _async_httpx_client during cleanup
                logger.debug("gemini_session_close_warning", error=str(e))
            finally:
                self._session_ctx = None
                self._session = None

        logger.info("gemini_live_session_closed")

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _build_config(
        self,
        system_instruction: str,
        voice_name: str,
    ) -> types.LiveConnectConfig:
        """
        Builds a LiveConnectConfig from the given parameters.

        Key fields
        ----------
        response_modalities   — "AUDIO" requests audio output from both classic
                                and native-audio model variants.
        output_audio_transcription — enables a parallel text transcript of the
                                model's audio output.  Without this the native
                                audio model (gemini-2.5-flash-native-audio-*)
                                produces audio bytes only; handle_gemini_text
                                never fires and the UI transcript stays empty.
        generation_config.temperature — wires the value from .env / settings
                                into every session (was previously ignored).
        """
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            generation_config=types.GenerationConfig(
                temperature=settings.gemini.temperature,
            ),
            # Restored: removing this entirely (testing whether our custom VAD
            # tuning caused the stall issue) made things WORSE, not better —
            # confirmed live: mic level meter showed real speech being
            # captured and sent, but Gemini's own DEFAULT sensitivity never
            # even registered it as speech at all (zero transcription). HIGH
            # sensitivity is necessary for reliable detection with this
            # mic/audio setup, not the cause of the separate stall issue —
            # that hypothesis is now ruled out. silence_duration_ms=100 is a
            # different, unrelated setting (how long to wait after silence
            # before ending the turn, not detection sensitivity) and stays.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    silence_duration_ms=100,
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=system_instruction)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        )

    async def _reconnect(self) -> None:
        """Tears down the current WebSocket session and opens a fresh one."""
        if self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("gemini_reconnect_old_session_close_warning", error=str(e))
            finally:
                self._session_ctx = None
                self._session = None

        self._session_ctx = self._client.aio.live.connect(
            model=settings.gemini.live_model,
            config=self._build_config(
                self._connect_system_instruction,
                self._connect_voice_name,
            ),
        )
        self._session = await self._session_ctx.__aenter__()
        logger.info("gemini_live_session_reconnected", session_id=self._connect_session_id)

    async def force_reconnect(self) -> None:
        """
        Public entry point for a caller-initiated reconnect — used by the
        turn-stall watchdog (a turn silently never got a response) and by the
        go_away handler (Gemini is about to drop the connection on its own).
        Just delegates to the same reconnect logic the retry loop already
        uses internally, so both paths stay consistent.

        Note: the still-running receive loop may independently notice the old
        session closing and attempt its own retry-driven reconnect shortly
        after this returns. Harmless — worst case is one redundant extra
        reconnect, not a crash or a stuck state — and not worth a locking
        mechanism for what should be a rare edge case (stalled turn / go_away).
        The flag below just keeps that redundant echo from surfacing a
        confusing duplicate "Reconnecting..." message to the user.
        """
        self._external_reconnect_pending = True
        await self._reconnect()

    # ──────────────────────────────────────────────────────────
    # Receive loop  (resilient — retries on transient failure)
    # ──────────────────────────────────────────────────────────

    async def _receive_loop(self, session_id: str) -> None:
        """
        Continuously receives messages from the Gemini Live WebSocket and
        dispatches them to registered callbacks.

        Failure handling
        ----------------
        • asyncio.CancelledError  — always re-raised; never retried (deliberate cancel).
        • Any other Exception     — treated as a transient WebSocket error and retried
          up to _MAX_RETRIES times with exponential back-off (_RETRY_DELAYS).
          Before each retry the _on_retry callback is fired so the UI can display
          "Reconnecting… (attempt N / max_retries)".
        • After all retries are exhausted — _on_turn(error) is called so the
          ConversationManager can clean up and close the client connection.
        • self._is_closed = True  — set by close() to short-circuit any retry.
        """
        for attempt in range(1, _MAX_RETRIES + 2):   # attempts 1 … _MAX_RETRIES+1
            if self._is_closed:
                logger.debug("gemini_receive_loop_exiting_on_close", session_id=session_id)
                break

            # ── From attempt 2 onward: notify, back-off, then reconnect ──
            if attempt > 1:
                delay = _RETRY_DELAYS[attempt - 2]    # index 0-based: attempt 2→delay[0]
                logger.warning(
                    "gemini_receive_loop_reconnecting",
                    session_id=session_id,
                    attempt=attempt - 1,   # human-readable: "retry attempt 1 of 3"
                    max_retries=_MAX_RETRIES,
                    delay_s=delay,
                )

                # Notify registered callback (UI update) — unless this retry
                # is just the expected echo of an external force_reconnect()
                # (watchdog/go_away) that already fixed things. Consume the
                # flag either way so a genuinely new failure afterward still
                # notifies normally.
                if self._on_retry and not self._external_reconnect_pending:
                    try:
                        await self._on_retry(attempt - 1, _MAX_RETRIES)
                    except Exception as cb_err:
                        logger.debug("retry_callback_error", error=str(cb_err))
                self._external_reconnect_pending = False

                await asyncio.sleep(delay)

                if self._is_closed:
                    break

                try:
                    await self._reconnect()
                except Exception as reconnect_err:
                    logger.error(
                        "gemini_reconnect_failed",
                        session_id=session_id,
                        attempt=attempt - 1,
                        error=str(reconnect_err),
                    )
                    # If this was the last allowed attempt, give up
                    if attempt > _MAX_RETRIES:
                        if self._on_turn:
                            await self._on_turn(str(reconnect_err))
                    continue   # retry the outer loop (attempt counter will hit the guard)

            # ── Run the receive generator ──────────────────────────────
            try:
                # The SDK's receive() generator breaks/exits by design when a turn
                # is completed (turn_complete=True). We wrap it in a persistent
                # while loop so that we automatically re-enter receive() for the
                # next conversation turn.
                while not self._is_closed:
                    async for response in self._session.receive():
                        if self._is_closed:
                            return
                        await self._dispatch_response(response, session_id)

                    # Generator completed cleanly (one turn complete).
                    # Loop back to listen for the next turn if session is active.
                    logger.debug("gemini_receive_turn_generator_completed", session_id=session_id)
                
                # Exited the outer loop cleanly
                logger.info("gemini_receive_stream_ended_cleanly", session_id=session_id)
                break

            except asyncio.CancelledError:
                # Deliberate cancellation from close() — propagate immediately, no retry
                logger.debug("gemini_receive_loop_cancelled", session_id=session_id)
                raise

            except Exception as e:
                if self._is_closed:
                    break

                logger.error(
                    "gemini_receive_loop_error",
                    session_id=session_id,
                    error=str(e),
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                )

                if attempt > _MAX_RETRIES:
                    # All retries exhausted — tell the ConversationManager to clean up
                    logger.error(
                        "gemini_receive_loop_all_retries_exhausted",
                        session_id=session_id,
                    )
                    if self._on_turn:
                        await self._on_turn(str(e))
                    break
                # else: fall through to next iteration which will reconnect

    async def _safe_callback(
        self,
        name: str,
        callback,
        session_id: str,
        *args,
    ) -> None:
        """
        Invokes a single registered callback with *args, isolating its exception
        from the surrounding parse pipeline.  A crashing audio callback will no
        longer suppress the turn-complete signal, and vice versa.
        """
        if not callback:
            return
        try:
            await callback(*args)
        except Exception as e:
            logger.error(
                "gemini_callback_error",
                callback=name,
                error=str(e),
                session_id=session_id,
            )

    async def _dispatch_response(self, response, session_id: str) -> None:
        """
        Parses a single Gemini Live response frame and dispatches to callbacks.

        Defence layers
        --------------
        1. getattr() with safe defaults on every SDK attribute — no bare dot
           access that can raise AttributeError when a field is absent.
        2. Per-callback isolation via _safe_callback — a crashing handler
           never suppresses other signals in the same frame.
        3. Unrecognised frames are logged at DEBUG (not silently dropped)
           so unknown future fields surface cleanly.

        Deliberately NOT logging a structural line on every frame here —
        this fires on every audio chunk of every response (the hottest path
        in the app) and was measurably adding overhead for no actionable
        gain beyond what on_audio/on_text/on_turn already surface.
        """
        # ── go_away: Gemini warning it will drop this connection soon ─────────
        # Previously fell through to the unrecognised-frame branch below and
        # was silently ignored. Confirmed in real testing: this frame did
        # arrive (time_left='50s') ahead of a real disconnect, and nothing
        # acted on it. Handled first, before the raw_data/server_content
        # branching, since it isn't audio or model content.
        go_away = getattr(response, "go_away", None)
        if go_away:
            time_left = getattr(go_away, "time_left", None)
            logger.warning("gemini_go_away_received", session_id=session_id, time_left=str(time_left))
            await self._safe_callback("on_go_away", self._on_go_away, session_id, str(time_left))
            return

        raw_data       = getattr(response, "data",           None)
        server_content = getattr(response, "server_content", None)

        # ── Path 1: Native audio (gemini-2.5-flash-native-audio-* model) ─────
        # Audio bytes arrive at the top-level response.data field rather than
        # inside server_content.model_turn.parts[].inline_data.
        if raw_data:
            await self._safe_callback("on_audio", self._on_audio, session_id, raw_data)
            return

        # ── Path 2: Server content block ──────────────────────────────────────
        if not server_content:
            # Frame carries neither audio data nor server content — log it so
            # we can identify unexpected SDK response shapes without crashing.
            logger.debug(
                "gemini_response_unrecognised_frame",
                session_id=session_id,
                response_repr=repr(response)[:400],
            )
            return

        content = server_content

        # Barge-in / interruption detected server-side
        if getattr(content, "interrupted", False):
            logger.debug("gemini_interruption_signal", session_id=session_id)
            await self._safe_callback("on_interruption", self._on_interruption, session_id)
            return

        # Model turn — may contain inline audio chunks AND/OR transcript text.
        # Both are processed independently so a missing text field never blocks audio.
        model_turn = getattr(content, "model_turn", None)
        if model_turn:
            parts = getattr(model_turn, "parts", None) or []
            for part in parts:
                # Inline audio (classic model format — not native audio model)
                inline_data = getattr(part, "inline_data", None)
                if inline_data:
                    chunk = getattr(inline_data, "data", None)
                    if chunk:
                        await self._safe_callback(
                            "on_audio", self._on_audio, session_id, chunk
                        )

                # Text transcript
                text = getattr(part, "text", None)
                if text:
                    is_final = getattr(content, "turn_complete", False)
                    await self._safe_callback(
                        "on_text", self._on_text, session_id, text, is_final
                    )

        # Input audio transcription — Gemini transcribes the user's voice.
        # This arrives in server_content.input_transcription.text and is the
        # server-side ground truth for what the user actually said.
        input_transcription = getattr(content, "input_transcription", None)
        if input_transcription:
            user_text = getattr(input_transcription, "text", None)
            if user_text:
                logger.debug("gemini_user_voice_transcribed", text=user_text, session_id=session_id)
                await self._safe_callback(
                    "on_user_transcript", self._on_user_transcript, session_id, user_text
                )

        # Turn-complete signal — processed last so audio/text callbacks always
        # fire before the ConversationManager transitions state.
        if getattr(content, "turn_complete", False):
            logger.debug("gemini_turn_complete", session_id=session_id)
            await self._safe_callback("on_turn", self._on_turn, session_id, None)

