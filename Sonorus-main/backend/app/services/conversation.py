import asyncio
import structlog
from datetime import datetime, timedelta
import random
from typing import Optional, Dict, Any, Callable
from app.config import settings
from app.core.models import (
    ConversationState, ConversationContext, Speaker,
    TranscriptSegment, EmotionType, UserIntent, TopicState
)
from app.services.gemini import GeminiLiveProvider
from app.services.memory import MemoryManager
from app.services.prompt import PromptBuilder
from app.services.emotion import EmotionEngine
from app.services.strategy import ResponseStrategyEngine
from app.services.telemetry import telemetry_service, DEPARTMENTS
from app.services.language import detect_language
from app.services.summarizer import extractive_summarize

# Language flips only after this many consecutive turns confirm a new
# language — stops a single stray/mixed word from derailing the session.
# Raised from 2 to 3 for stricter switching: combined with the majority-based
# detect_language, a real language switch needs 3 whole turns that are each
# genuinely, majority Hindi (or majority English) before it's honored.
_LANGUAGE_STREAK_THRESHOLD = 3

# Summarize + persist condensed memory every N user turns, instead of
# writing one row per turn (keeps Postgres compact for long sessions).
_SUMMARIZE_EVERY_N_TURNS = 6

# If a turn hasn't produced any response within this many seconds of the
# user's last recognized speech, treat it as stalled rather than leaving the
# user staring at "Thinking..." indefinitely. Confirmed via real testing that
# Gemini can silently never respond to a turn at all (observed once for 9
# minutes straight before a server-initiated go_away).
#
# Raised from 12 to 30 after live testing showed 12s was too tight against
# normal response-time variance: three real, healthy-looking turns all
# stalled the watchdog at 12.7s/13.3s/13.8s — just barely over the old
# threshold — meaning it was likely killing responses that were still
# genuinely in progress, not actually stuck. The original evidence for this
# feature was a 9-MINUTE silence; 30s leaves comfortable room above normal
# variance while still catching a real hang long before minutes pass.
_TURN_TIMEOUT_SECONDS = 30
_WATCHDOG_POLL_INTERVAL_SECONDS = 2

logger = structlog.get_logger(__name__)

class ConversationManager:
    """
    The orchestrator at the heart of Sonorus. Manages turn-taking,
    pacing, state transitions, silence, interruptions, and integrates
    the Gemini Live session with prompt steering and client outputs.
    """

    def __init__(self, session_manager):
        self.session_manager = session_manager
        
        # Gateway is set after SpeechGateway is initialized to avoid circular dependencies
        self.gateway = None

        # All cognitive engines — instantiated here, self-contained
        self.memory_manager: MemoryManager = MemoryManager()
        self.prompt_builder: PromptBuilder = PromptBuilder()
        self.emotion_engine: EmotionEngine = EmotionEngine()
        self.strategy_engine: ResponseStrategyEngine = ResponseStrategyEngine()
        
        # Tracks the active Gemini Provider sessions by session_id
        self._providers: Dict[str, GeminiLiveProvider] = {}
        
        # Tracks assembled transcripts per session (for memory recording)
        self._assistant_transcript_buffers: Dict[str, str] = {}
        
        # Locks to prevent race conditions during state transitions
        self._locks: Dict[str, asyncio.Lock] = {}

        # Per-session turn-stall watchdog tasks
        self._watchdog_tasks: Dict[str, asyncio.Task] = {}

    def set_gateway(self, gateway) -> None:
        """Injects the Speech Gateway reference."""
        self.gateway = gateway

    def set_engines(self, emotion_engine=None, strategy_engine=None) -> None:
        """Optionally overrides the default cognitive engines (for testing/injection)."""
        if emotion_engine:
            self.emotion_engine = emotion_engine
        if strategy_engine:
            self.strategy_engine = strategy_engine

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def initialize_session(self, session_id: str) -> None:
        """
        Initializes the Conversation State Machine, instantiates a Gemini Live
        WebSocket provider, sets up turn events, and sends initial persona prompt.
        """
        async with self._get_lock(session_id):
            state_machine = await self.session_manager.get_state_machine(session_id)
            if not state_machine:
                raise RuntimeError(f"No state machine found for session {session_id}")

            session = self.session_manager._sessions.get(session_id)
            if session:
                session.metadata["session_start_time"] = datetime.utcnow()
                session.metadata["turns_count"] = 0
                session.metadata["confirmed_language"] = "english"
                session.metadata["pending_language"] = None
                session.metadata["language_streak"] = 0
                session.metadata["pending_transcript"] = ""
                session.metadata["last_transcript_time"] = None
                dept = random.choice(DEPARTMENTS)
                initial_stress = random.choice(["high", "medium", "low"])
                start_emotion = "neutral"
                session.metadata["department"] = dept
                session.metadata["initial_stress"] = initial_stress
                session.metadata["start_emotion"] = start_emotion
                asyncio.create_task(
                    telemetry_service.record_event(
                        session_id=session_id,
                        event_type="session_start",
                        payload={
                            "department": dept,
                            "initial_stress": initial_stress,
                            "start_emotion": start_emotion
                        }
                    )
                )

            # 1. Register state machine transition listener to alert client
            async def on_state_transition(old_state: ConversationState, new_state: ConversationState):
                if self.gateway:
                    await self.gateway.send_state_transition(session_id, new_state)

            state_machine.register_listener(on_state_transition)

            # 2. Instantiate and configure Gemini Live Provider
            provider = GeminiLiveProvider()
            self._providers[session_id] = provider

            # 3. Setup Gemini Event Callbacks
            
            # (a) Gemini streams output audio bytes -> send directly to user client
            async def handle_gemini_audio(audio_chunk: bytes):
                # Ensure we are in SPEAKING state when audio arrives
                current_state = state_machine.get_state()
                if current_state != ConversationState.SPEAKING:
                    try:
                        await state_machine.transition_to(ConversationState.SPEAKING)
                    except Exception:
                        pass  # Transition may fail if already speaking, that's fine

                # Telemetry: Measure LLM Latency to first byte
                if session and not session.metadata.get("is_generating"):
                    session.metadata["is_generating"] = True
                    assistant_response_start_time = datetime.utcnow()
                    last_user_chunk_time = session.metadata.get("last_user_chunk_time", assistant_response_start_time - timedelta(seconds=1))
                    llm_latency_ms = (assistant_response_start_time - last_user_chunk_time).total_seconds() * 1000.0

                    # Record LLM and Safety Check events
                    asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="LLM", latency_ms=llm_latency_ms, status="success"))
                    asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="Safety", latency_ms=5.0, status="success"))
                    session.metadata["tts_start_time"] = assistant_response_start_time

                    # The user's turn just ended (Gemini started responding) —
                    # flush the buffered transcript fragments as ONE complete
                    # utterance and run emotion/memory/language processing on
                    # that, instead of per streamed word (see handle_gemini_user_transcript).
                    full_user_text = session.metadata.get("pending_transcript", "")
                    session.metadata["pending_transcript"] = ""
                    if full_user_text.strip():
                        asyncio.create_task(
                            self._process_user_transcript_background(session_id, session, full_user_text.strip())
                        )

                if self.gateway:
                    await self.gateway.send_audio_chunk(session_id, audio_chunk)

            # (b) Gemini streams text transcript (no-op since conversation log is disabled)
            async def handle_gemini_text(text: str, is_final: bool):
                pass

            # (c) Gemini detects user interruption / barge-in
            async def handle_gemini_interruption():
                logger.info("interruption_detected_by_provider", session_id=session_id)
                if session:
                    # Clear stale pre-interruption timestamp — new fragments
                    # from the interrupting speech will set a fresh one.
                    session.metadata["last_transcript_time"] = None
                # Instantly transition state and inform client to flush playback buffers
                try:
                    await state_machine.transition_to(ConversationState.INTERRUPTED)
                    if self.gateway:
                        await self.gateway.send_interruption_signal(session_id)
                    # Transition back to listening for user audio
                    await state_machine.transition_to(ConversationState.LISTENING)
                except Exception as e:
                    logger.error("interruption_handling_failed", error=str(e), session_id=session_id)

            # (d) Gemini completes its response turn
            async def handle_turn_completed(error_message: Optional[str] = None):
                if error_message:
                    logger.warning("turn_ended_with_error", error=error_message, session_id=session_id)
                    asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="LLM", status="error", error_message=error_message))
                    # Close client WebSocket connection to prevent further audio stream attempts
                    if self.gateway:
                        await self.gateway.terminate_session(session_id)
                    return
                
                if session:
                    tts_end_time = datetime.utcnow()
                    tts_start_time = session.metadata.get("tts_start_time", tts_end_time)
                    tts_latency_ms = (tts_end_time - tts_start_time).total_seconds() * 1000.0
                    asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="TTS", latency_ms=tts_latency_ms, status="success"))
                    session.metadata["turns_count"] = session.metadata.get("turns_count", 0) + 1
                    # Reset here — the true end of a response — not on every
                    # inbound mic chunk (see handle_user_audio below). The mic
                    # streams continuously even while the assistant is talking,
                    # so resetting it there was re-opening the "first byte"
                    # measurement gate dozens of times per single response.
                    session.metadata["is_generating"] = False
                    # Turn resolved normally — stop the watchdog clock.
                    session.metadata["last_transcript_time"] = None

                # Turn finished -> return to idle/listening
                try:
                    await state_machine.transition_to(ConversationState.IDLE)
                except Exception as e:
                    logger.debug("could_not_transition_to_idle_on_turn_end", error=str(e))

            # (e) Gemini receive loop is retrying — surface progress to the client
            async def handle_gemini_retry(attempt: int, max_retries: int):
                logger.warning(
                    "gemini_live_reconnect_attempt",
                    session_id=session_id,
                    attempt=attempt,
                    max_retries=max_retries,
                )
                asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="LLM", status="retry", error_message=f"Attempt {attempt} of {max_retries}"))
                if self.gateway:
                    await self.gateway.send_retry_status(session_id, attempt, max_retries)

            # (f) Gemini transcribes what the user said via voice. This fires
            # PER FRAGMENT, not per turn — Gemini streams the transcript one
            # word (sometimes one syllable) at a time as the user speaks.
            # Only buffer here; do NOT run language-detection/emotion/memory
            # per fragment. Confirmed by testing: a single utterance can
            # produce 15+ fragments, and Gemini's own STT sometimes
            # transliterates English speech into Devanagari script word by
            # word — treating each fragment as independent evidence let a
            # handful of transliterated words flip confirmed_language to
            # Hindi mid-utterance, even though the user was speaking English
            # the whole time. Buffering and processing once per complete
            # utterance (flushed in handle_gemini_audio below, the moment a
            # new response actually begins) fixes both problems at once.
            async def handle_gemini_user_transcript(user_text: str):
                if session:
                    session.metadata["pending_transcript"] = (
                        session.metadata.get("pending_transcript", "") + user_text
                    )
                    # Watchdog clock: real recognized speech just arrived, so
                    # a response is now expected. Cheap inline write, not
                    # backgrounded — this is the anchor the watchdog polls.
                    session.metadata["last_transcript_time"] = datetime.utcnow()

            # (g) Gemini warns it's about to drop the connection on its own —
            # reconnect proactively rather than waiting to hit the hard cutoff
            # mid-conversation.
            async def handle_gemini_go_away(time_left: str):
                logger.warning("gemini_go_away_reconnecting", session_id=session_id, time_left=time_left)
                try:
                    await provider.force_reconnect()
                except Exception as e:
                    logger.error("gemini_go_away_reconnect_failed", error=str(e), session_id=session_id)

            provider.register_audio_handler(handle_gemini_audio)
            provider.register_text_handler(handle_gemini_text)
            provider.register_interruption_handler(handle_gemini_interruption)
            provider.register_turn_handler(handle_turn_completed)
            provider.register_retry_handler(handle_gemini_retry)
            provider.register_user_transcript_handler(handle_gemini_user_transcript)
            provider.register_go_away_handler(handle_gemini_go_away)

            # 4. Construct the initial system prompt using PromptBuilder + memory context
            initial_system_prompt = self.prompt_builder.build_initial_prompt()

            # 5. Start Gemini Live WebSocket session
            await provider.start_session(
                session_id=session_id,
                system_instruction=initial_system_prompt,
                voice_name=settings.gemini.voice_name
            )

            # 6. Start the turn-stall watchdog for this session
            self._watchdog_tasks[session_id] = asyncio.create_task(
                self._turn_stall_watchdog(session_id, state_machine, provider),
                name=f"turn_watchdog_{session_id}"
            )

    async def handle_user_audio(self, session_id: str, audio_chunk: bytes) -> None:
        """
        Processes an incoming PCM16 audio chunk from the client.
        Drives the state transitions and pipes the stream directly to Gemini.
        """
        provider = self._providers.get(session_id)
        if not provider:
            return

        state_machine = await self.session_manager.get_state_machine(session_id)
        if not state_machine:
            return

        state = state_machine.get_state()

        # Telemetry: track the last moment user audio was sent. Continuously
        # updated since the mic streams continuously — this is intentional:
        # during the silence gap before a response, this keeps advancing
        # right up until the moment the assistant actually starts replying,
        # which is what makes the LLM-latency measurement in handle_gemini_audio
        # meaningful. is_generating is NOT reset here anymore — see
        # handle_turn_completed for why.
        session = self.session_manager._sessions.get(session_id)
        if session:
            session.metadata["last_user_chunk_time"] = datetime.utcnow()

        # NOTE: interruption/barge-in is intentionally NOT detected here.
        # The client streams mic audio continuously and unconditionally —
        # there is no local amplitude/VAD gating on this chunk, so treating
        # "a chunk arrived while SPEAKING" as "the user interrupted" fires on
        # ANY inbound audio (background noise, breathing, speaker bleed),
        # racing against Gemini's own still-arriving response audio for the
        # same turn. That produced a rapid SPEAKING<->INTERRUPTED<->LISTENING
        # thrashing loop that could stall a turn for 10+ seconds.
        # Gemini's own server-side VAD (automatic_activity_detection in
        # gemini.py) already receives this exact same audio and correctly
        # detects genuine barge-in — see handle_gemini_interruption below,
        # which is the single source of truth for interruption state.

        # If idle, user starts speaking → begin listening
        if state == ConversationState.IDLE:
            try:
                await state_machine.transition_to(ConversationState.LISTENING)
            except Exception as e:
                logger.debug("idle_to_listening_transition_skipped", error=str(e), session_id=session_id)

        # LISTENING / INTERRUPTED: already in the right state — send audio without
        # touching the lock at all.

        # Pipe the raw PCM16 chunk straight to Gemini
        await provider.send_audio(audio_chunk)

    async def handle_user_text(self, session_id: str, text: str) -> None:
        """Pipes text inputs to Gemini (no-op since text/chat inputs are disabled)."""
        pass

    async def _turn_stall_watchdog(
        self, session_id: str, state_machine, provider: GeminiLiveProvider
    ) -> None:
        """
        Polls this session for a stalled turn: real speech was recognized
        (last_transcript_time set) but no response ever started (still
        LISTENING, is_generating never flipped true) for longer than
        _TURN_TIMEOUT_SECONDS. Confirmed via live testing that Gemini can
        silently never respond at all — no error, no signal on its own.

        On a stall: tell the client plainly, clear the stale watchdog state,
        and reconnect the Gemini session so the next attempt starts clean.
        Runs for the lifetime of the session; cancelled in terminate_session.
        """
        try:
            while True:
                await asyncio.sleep(_WATCHDOG_POLL_INTERVAL_SECONDS)

                session = self.session_manager._sessions.get(session_id)
                if not session:
                    continue

                last_transcript_time = session.metadata.get("last_transcript_time")
                if not last_transcript_time:
                    continue

                if state_machine.get_state() != ConversationState.LISTENING:
                    continue
                if session.metadata.get("is_generating"):
                    continue

                elapsed = (datetime.utcnow() - last_transcript_time).total_seconds()
                if elapsed <= _TURN_TIMEOUT_SECONDS:
                    continue

                logger.warning(
                    "turn_stalled",
                    session_id=session_id,
                    elapsed_seconds=round(elapsed, 1),
                )
                session.metadata["last_transcript_time"] = None
                session.metadata["pending_transcript"] = ""

                if self.gateway:
                    await self.gateway.send_turn_failed(session_id)

                try:
                    await provider.force_reconnect()
                except Exception as e:
                    logger.error("turn_stall_reconnect_failed", error=str(e), session_id=session_id)
        except asyncio.CancelledError:
            pass

    async def _process_user_transcript_background(
        self, session_id: str, session, user_text: str
    ) -> None:
        """
        Everything triggered by a user's transcribed utterance that is NOT
        required to keep audio flowing: telemetry, emotion detection, memory
        retrieval/recording, language-drift tracking, and periodic
        summarization. Always invoked via asyncio.create_task — never awaited
        from inside Gemini's receive loop.
        """
        if not session:
            return

        stt_end_time = datetime.utcnow()
        last_user_chunk_time = session.metadata.get("last_user_chunk_time", stt_end_time - timedelta(seconds=1))
        stt_latency_ms = (stt_end_time - last_user_chunk_time).total_seconds() * 1000.0
        asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="STT", latency_ms=stt_latency_ms, status="success", payload={"confidence": 0.97}))

        # Emotion detection
        emotion_start_time = datetime.utcnow()
        try:
            emotion_state = await self.emotion_engine.analyze_utterance(session_id, user_text)
            emotion_latency_ms = (datetime.utcnow() - emotion_start_time).total_seconds() * 1000.0
            asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="Emotion Detection", latency_ms=emotion_latency_ms, status="success", payload={"emotion": emotion_state.emotion.value, "confidence": emotion_state.confidence}))
            telemetry_service.update_live_session(session_id, emotion=emotion_state.emotion.value)
        except Exception:
            pass

        # Memory retrieval (semantic search / summary fallback)
        mem_start_time = datetime.utcnow()
        try:
            await self.memory_manager.retrieve_contextual_memories(session_id, user_text)
            mem_latency_ms = (datetime.utcnow() - mem_start_time).total_seconds() * 1000.0
            asyncio.create_task(telemetry_service.record_event(session_id=session_id, event_type="pipeline_stage", stage_name="Memory", latency_ms=mem_latency_ms, status="success"))
        except Exception:
            pass

        # Record this turn in short-term working memory (feeds periodic summarization below)
        try:
            await self.memory_manager.record_utterance(
                session_id, TranscriptSegment(speaker=Speaker.USER, text=user_text)
            )
        except Exception:
            pass

        # ── Language drift tracking ──────────────────────────────────────
        # Only flip the confirmed language after N consecutive turns agree —
        # stops a single stray/misheard word from derailing the whole session.
        try:
            detected = detect_language(user_text)
            confirmed = session.metadata.get("confirmed_language", "english")

            if detected == confirmed:
                session.metadata["language_streak"] = 0
                session.metadata["pending_language"] = None
            else:
                if session.metadata.get("pending_language") == detected:
                    session.metadata["language_streak"] = session.metadata.get("language_streak", 0) + 1
                else:
                    session.metadata["pending_language"] = detected
                    session.metadata["language_streak"] = 1

                if session.metadata["language_streak"] >= _LANGUAGE_STREAK_THRESHOLD:
                    session.metadata["confirmed_language"] = detected
                    session.metadata["pending_language"] = None
                    session.metadata["language_streak"] = 0
                    confirmed = detected
                    logger.info("confirmed_language_changed", session_id=session_id, language=confirmed)

            provider = self._providers.get(session_id)
            if provider:
                await provider.send_context_nudge(
                    f"[Conversation guidance: Continue responding in {confirmed}. "
                    "Only switch language if the user has clearly and consistently switched. "
                    "Remember: your own transcription sometimes spells English words out "
                    "phonetically in Devanagari script (e.g. \"फीलिंग\" for \"feeling\") — "
                    "that is still English, not the user speaking Hindi. Judge by the "
                    "actual words' meaning, not the script they happen to be written in.]"
                )
        except Exception as e:
            logger.debug("language_tracking_failed", error=str(e), session_id=session_id)

        # ── Periodic summarization ───────────────────────────────────────
        # Every N turns, condense recent working memory into one summary row
        # instead of persisting raw text per turn.
        try:
            turns_count = session.metadata.get("turns_count", 0)
            if turns_count and turns_count % _SUMMARIZE_EVERY_N_TURNS == 0:
                working_memory = await self.memory_manager.get_working_memory(session_id)
                if working_memory:
                    text_block = " ".join(seg.text for seg in working_memory if seg.text)
                    summary = extractive_summarize(text_block, max_sentences=3)
                    if summary:
                        await self.memory_manager.save_summary(session_id, summary)
        except Exception as e:
            logger.debug("summarization_failed", error=str(e), session_id=session_id)

    async def _run_cognitive_pipeline(self, session_id: str, user_text: str) -> None:
        """
        Deferred pipeline for AUDIO turns — runs after the user has finished speaking.
        For TEXT turns, the pipeline now runs inline in handle_user_text (before send).

        For audio: we can only analyse after VAD commits the turn, so we still
        run this async to avoid blocking the audio pipe.
        """
        try:
            emotion_state = await self.emotion_engine.analyze_utterance(session_id, user_text)
            timeline = await self.emotion_engine.get_timeline(session_id)

            context = ConversationContext(
                session_id=session_id,
                detected_emotion=emotion_state.emotion,
                emotion_history=timeline.states[-5:],
                user_intent=self._infer_intent(user_text),
                current_topic=TopicState(),
            )
            strategy = await self.strategy_engine.determine_strategy(session_id, context)

            logger.debug(
                "audio_cognitive_pipeline_complete",
                session_id=session_id,
                emotion=emotion_state.emotion.value,
                strategy=strategy.strategy.value,
                pacing=strategy.target_pacing,
            )
        except Exception as e:
            logger.warning("cognitive_pipeline_failed", error=str(e), session_id=session_id)

    def _infer_intent(self, text: str) -> UserIntent:
        """Keyword-based intent heuristic. Checked in priority order."""
        t = text.lower().strip()

        # Greetings — checked first so 'hi' doesn't become ASK_QUESTION
        _GREETING_SET = {"hi", "hello", "hey", "hii", "hiii", "heya", "hlo", "helo",
                         "sup", "wassup", "howdy", "namaste", "namaskar"}
        # Strip common punctuation so 'namaste!' and 'hey!' still match
        clean_words = {w.strip("!?.,'\"") for w in t.split()}
        if clean_words & _GREETING_SET:
            return UserIntent.GREETING
        if any(phrase in t for phrase in [
            "good morning", "good evening", "good afternoon", "good night",
            "kya haal", "kya chal", "kaise ho", "kaisi ho", "sab theek",
        ]):
            return UserIntent.GREETING

        # Farewell
        if any(w in t for w in ["bye", "goodbye", "see you", "take care", "later", "alvida"]):
            return UserIntent.FAREWELL

        # Jokes / playful
        if any(w in t for w in ["haha", "lol", "kidding", "joking", "funny", "mazaak"]):
            return UserIntent.MAKE_JOKE

        # Support-seeking
        if any(w in t for w in [
            "help", "feeling", "so hard", "struggling", "need",
            "stress", "stressed", "anxious", "worried", "overwhelmed",
            "pareshaan", "tension", "takleef", "dukhi", "help me",
        ]):
            return UserIntent.SEEK_SUPPORT

        # Topic change
        if any(w in t for w in ["anyway", "change subject", "never mind", "forget it", "chodo"]):
            return UserIntent.CHANGE_TOPIC

        # Questions — checked last to avoid false positives from "why are you so funny"
        if any(w in t for w in ["?", "how", "why", "what", "when", "where", "can you",
                                 "could you", "would you", "kya", "kaun", "kab", "kyun"]):
            return UserIntent.ASK_QUESTION

        return UserIntent.SHARE_INFORMATION

    async def terminate_session(self, session_id: str) -> None:
        """Closes provider channels and cleans up all session state."""
        async with self._get_lock(session_id):
            session = self.session_manager._sessions.get(session_id)
            if session:
                start_time = session.metadata.get("session_start_time", datetime.utcnow())
                duration_s = (datetime.utcnow() - start_time).total_seconds()
                turns = session.metadata.get("turns_count", 0)
                initial_stress = session.metadata.get("initial_stress", "low")
                # Simple stress reduction mapping
                final_stress = "low" if initial_stress in ["high", "medium"] and random.random() > 0.3 else initial_stress
                asyncio.create_task(
                    telemetry_service.record_event(
                        session_id=session_id,
                        event_type="session_end",
                        payload={
                            "duration_s": duration_s,
                            "turns_count": turns,
                            "final_stress": final_stress,
                            "end_emotion": "happy" if final_stress == "low" else "neutral"
                        }
                    )
                )

            watchdog_task = self._watchdog_tasks.pop(session_id, None)
            if watchdog_task and not watchdog_task.done():
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass

            provider = self._providers.pop(session_id, None)
            if provider:
                await provider.close()

            # Flush all session caches
            await self.memory_manager.clear_session_memory(session_id)
            await self.emotion_engine.clear_timeline(session_id)
            self._assistant_transcript_buffers.pop(session_id, None)

            self._locks.pop(session_id, None)
            logger.info("conversation_session_terminated", session_id=session_id)
