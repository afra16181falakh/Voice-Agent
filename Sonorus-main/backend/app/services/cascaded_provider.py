import asyncio
import io
import json
import threading
import urllib.request
import urllib.error
import wave
from typing import Callable, Awaitable, Optional

import numpy as np
import structlog

from app.config import settings
from app.core.interfaces.provider import IConversationProvider
from app.services.language import detect_language
from app.services.knowledge import retrieve_kb_context
from app.services.tools import all_tool_schemas, execute_tool

logger = structlog.get_logger(__name__)

# Bounded tool-call loop: LLM requests a tool -> we execute it -> feed the
# result back -> LLM either replies with text or requests another tool.
# Capped so a misbehaving/looping model can't stall a turn indefinitely.
_MAX_TOOL_ROUNDS = 3

# ── Simple energy-based turn-boundary detection ─────────────────────────
# Gemini has its own server-side VAD; leaving Gemini means we lose that, so
# this replaces it. Deliberately simple (RMS threshold + debounce), same
# category of approach already proven client-side for the "Thinking..."
# indicator (Round 3 of the plan) -- tunable later exactly like Gemini's
# silence_duration_ms was tuned repeatedly this project. Threshold itself
# now lives in settings.stt.vad_speech_rms_threshold (see config.py) --
# reported live as needing near-shouting at the original hardcoded 0.02.
# Lowered from 0.6 now that the VAD threshold (settings.stt.
# vad_speech_rms_threshold) is properly calibrated above this room's actual
# noise floor -- background noise no longer keeps resetting this timer, so
# it's safe to react faster once you actually stop talking, same tuning
# lever as Gemini's own silence_duration_ms (tuned down to 100ms there).
_SILENCE_DURATION_SECONDS = 0.4
# Raised from 0.3 -- confirmed live: with the VAD threshold lowered (to fix
# the earlier "have to shout" issue), brief background noise/breath now
# crosses it easily, and 0.3s wasn't enough to filter that out from real
# speech. Result was many short (~1-2s) "utterances" triggering full STT
# passes on what was actually noise -- Whisper correctly rejected them
# (see cascaded_stt_empty_transcript), but repeatedly, for over a minute,
# with no signal to the user that anything was happening. Starting point,
# not a final answer -- the new logging above makes this tunable with real
# data instead of another guess.
_MIN_SPEECH_DURATION_SECONDS = 0.5

# Barge-in (interrupting a response already playing) requires this many
# consecutive seconds of above-threshold audio before it counts as a real
# interruption -- not a single instantaneous chunk. Without this, every
# reply got aborted within ~50-100ms of starting to speak, every single
# time (confirmed live): the VAD threshold is deliberately low (see
# vad_speech_rms_threshold) so normal speech registers without shouting,
# but that same low bar made barge-in fire on a single brief noise blip or
# the mic picking up Sonorus's own voice bleeding from the speakers the
# instant playback started.
_BARGE_IN_MIN_DURATION_SECONDS = 0.3

_OUT_SAMPLE_RATE = 24000  # matches frontend's existing OUT_SAMPLE_RATE, untouched

# ── Lazily-loaded, process-wide singletons ──────────────────────────────
# Model loading takes real seconds (see Phase A spike) -- load once, share
# across every session/provider instance rather than per-session.
_stt_model = None
_stt_lock = threading.Lock()
_piper_voices: dict = {}
_piper_lock = threading.Lock()


def _get_stt_model():
    global _stt_model
    if _stt_model is None:
        with _stt_lock:
            if _stt_model is None:
                from faster_whisper import WhisperModel
                logger.info("cascaded_stt_model_loading", model=settings.stt.model_size)
                _stt_model = WhisperModel(
                    settings.stt.model_size,
                    device=settings.stt.device,
                    compute_type=settings.stt.compute_type,
                )
    return _stt_model


def _get_piper_voice(voice_name: str):
    if voice_name not in _piper_voices:
        with _piper_lock:
            if voice_name not in _piper_voices:
                from piper import PiperVoice
                voice_path = f"{settings.tts.voice_dir}\\{voice_name}.onnx"
                logger.info("cascaded_tts_voice_loading", voice=voice_name)
                _piper_voices[voice_name] = PiperVoice.load(voice_path)
    return _piper_voices[voice_name]


def _rms(pcm16_chunk: bytes) -> float:
    if not pcm16_chunk:
        return 0.0
    arr = np.frombuffer(pcm16_chunk, dtype=np.int16).astype(np.float32) / 32768.0
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr ** 2)))


def _resample_pcm16(pcm_bytes: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not pcm_bytes:
        return pcm_bytes
    from scipy.signal import resample
    arr = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    n_dst = max(1, int(len(arr) * dst_rate / src_rate))
    out = resample(arr, n_dst)
    return np.clip(out, -32768, 32767).astype(np.int16).tobytes()


def _parse_openai_tool_calls(raw_tool_calls: Optional[list]) -> list:
    """Shared by Ollama (unused, no tool support) and Groq -- OpenAI wire
    shape: tool_calls[].function.arguments is a JSON STRING, not a dict."""
    from app.core.models import ToolCallRequest
    if not raw_tool_calls:
        return []
    parsed = []
    for tc in raw_tool_calls:
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except (json.JSONDecodeError, KeyError):
            args = {}
        parsed.append(ToolCallRequest(id=tc.get("id", ""), name=tc["function"]["name"], arguments=args))
    return parsed


def _ollama_chat_sync(messages: list[dict], tools: Optional[list[dict]] = None) -> tuple[dict, list]:
    # Ollama/local Llama 3.2 3B has no tool-calling support in Phase 1 --
    # `tools` is accepted for signature parity with the other backends but
    # silently ignored here; this is the documented fallback-only limitation.
    body = json.dumps({
        "model": settings.llm.model,
        "messages": messages,
        "stream": False,
        # Ollama's default keep_alive is 5 minutes -- any gap longer than
        # that between turns (very plausible: user thinking, testing,
        # talking to someone else) unloads the model, and the NEXT call
        # pays a ~7-10s cold-reload cost on top of normal generation time.
        # Confirmed live: a 38s response gap traced back to exactly this.
        # -1 keeps it loaded indefinitely -- only ~2GB, this machine has
        # 15.7GB RAM, no reason to ever unload it.
        "keep_alive": -1,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.llm.base_url}/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    content = result["message"]["content"].strip()
    return {"role": "assistant", "content": content}, []


def _groq_chat_sync(messages: list[dict], tools: Optional[list[dict]] = None) -> tuple[dict, list]:
    """Groq's API is OpenAI-compatible (chat/completions shape) -- same
    messages format we already build for Ollama/Gemini, just a different
    endpoint. Runs on Groq's custom LPU hardware: 394-1,000 tokens/sec,
    far faster than Gemini's text API or local CPU inference."""
    body_dict = {
        "model": settings.groq.model,
        "messages": messages,
    }
    if tools:
        body_dict["tools"] = tools
        body_dict["tool_choice"] = "auto"
    body = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions", data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.groq.api_key}",
            # Python's default urllib User-Agent gets flagged and blocked
            # by Cloudflare bot protection (403, error 1010) -- confirmed
            # directly. Same header added to Deepgram/Cartesia below.
            "User-Agent": "Sonorus/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("groq_http_error", status=e.code, body=error_body)
        raise
    message = result["choices"][0]["message"]
    tool_calls = _parse_openai_tool_calls(message.get("tool_calls"))
    # Persist the raw assistant message (including raw tool_calls, if any)
    # so it round-trips back through Groq unchanged on the next call.
    assistant_message = {"role": "assistant", "content": message.get("content") or ""}
    if message.get("tool_calls"):
        assistant_message["tool_calls"] = message["tool_calls"]
    return assistant_message, tool_calls


_gemini_client = None
_gemini_client_lock = threading.Lock()


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        with _gemini_client_lock:
            if _gemini_client is None:
                from google import genai
                _gemini_client = genai.Client(api_key=settings.gemini.api_key)
    return _gemini_client


def _gemini_tools_from_openai_shape(tools: list[dict]):
    """Converts our one canonical OpenAI-shaped tool schema list into
    Gemini's Tool/FunctionDeclaration objects -- confirmed directly against
    the installed SDK that parameters_json_schema accepts a raw JSON-Schema
    dict, no hand conversion to types.Schema needed."""
    from google.genai import types
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name=t["function"]["name"],
            description=t["function"]["description"],
            parameters_json_schema=t["function"]["parameters"],
        )
        for t in tools
    ])]


async def _gemini_chat_async(messages: list[dict], tools: Optional[list[dict]] = None) -> tuple[dict, list]:
    """
    Same role as _ollama_chat_sync, but the LLM stage is Gemini's plain
    text API instead of the local Llama model -- genuinely async network
    I/O (unlike the CPU-bound STT/TTS calls), so this is awaited directly
    rather than run via asyncio.to_thread.

    Transcodes our one canonical OpenAI-shaped message list (role/content,
    plus tool_calls on assistant messages, plus role="tool" results) into
    Gemini's Content/Part shape on every call -- confirmed directly against
    the installed SDK: Part.from_function_call(name, args) and
    Part.from_function_response(name, response) are the exact round-trip
    pair Gemini expects.
    """
    from google.genai import types

    system_text = None
    contents = []
    for m in messages:
        if m["role"] == "system":
            # Gemini takes one system_instruction, not inline system
            # messages -- concatenate if there's more than one (e.g. the
            # base persona prompt plus a pending language nudge).
            system_text = m["content"] if system_text is None else f"{system_text}\n\n{m['content']}"
        elif m["role"] == "tool":
            try:
                result = json.loads(m["content"])
            except (json.JSONDecodeError, TypeError):
                result = {"result": m["content"]}
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=m["name"], response=result)
            ]))
        elif m["role"] == "assistant" and m.get("tool_calls"):
            parts = []
            for tc in m["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except (json.JSONDecodeError, KeyError):
                    args = {}
                parts.append(types.Part.from_function_call(name=tc["function"]["name"], args=args))
            contents.append(types.Content(role="model", parts=parts))
        else:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

    config_kwargs = {"system_instruction": system_text, "temperature": settings.gemini.temperature}
    if tools:
        config_kwargs["tools"] = _gemini_tools_from_openai_shape(tools)

    client = _get_gemini_client()
    response = await client.aio.models.generate_content(
        model=settings.gemini.text_model,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    from app.core.models import ToolCallRequest
    import uuid as _uuid

    text_parts = []
    tool_calls = []
    raw_tool_calls_for_history = []
    for part in response.candidates[0].content.parts:
        if getattr(part, "function_call", None):
            fc = part.function_call
            call_id = f"call_{_uuid.uuid4().hex[:8]}"
            args = dict(fc.args) if fc.args else {}
            tool_calls.append(ToolCallRequest(id=call_id, name=fc.name, arguments=args))
            raw_tool_calls_for_history.append({
                "id": call_id, "type": "function",
                "function": {"name": fc.name, "arguments": json.dumps(args)},
            })
        elif getattr(part, "text", None):
            text_parts.append(part.text)

    assistant_message = {"role": "assistant", "content": "".join(text_parts)}
    if raw_tool_calls_for_history:
        assistant_message["tool_calls"] = raw_tool_calls_for_history
    return assistant_message, tool_calls


async def _run_llm(messages: list[dict], tools: Optional[list[dict]] = None) -> tuple[dict, list]:
    """Dispatches to whichever LLM backend settings.llm.provider selects.
    Returns (assistant_message: dict, tool_calls: list[ToolCallRequest])."""
    if settings.llm.provider == "groq":
        return await asyncio.to_thread(_groq_chat_sync, messages, tools)
    if settings.llm.provider == "gemini":
        return await _gemini_chat_async(messages, tools)
    return await asyncio.to_thread(_ollama_chat_sync, messages, tools)


async def _gemini_tts_async(text: str) -> tuple[bytes, int]:
    """
    Gemini's dedicated TTS model -- real emotional/expressive voice, unlike
    Piper. Response comes back as raw PCM16 (confirmed directly: mime_type
    "audio/l16; rate=24000; channels=1") inside the same
    candidates[0].content.parts[0].inline_data shape Gemini Live already
    uses for its classic (non-native-audio) audio path.
    """
    from google.genai import types

    client = _get_gemini_client()
    response = await client.aio.models.generate_content(
        model=settings.gemini.tts_model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.gemini.voice_name)
                )
            ),
        ),
    )
    part = response.candidates[0].content.parts[0]
    pcm_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or ""
    sample_rate = _OUT_SAMPLE_RATE
    for chunk in mime_type.split(";"):
        chunk = chunk.strip()
        if chunk.startswith("rate="):
            sample_rate = int(chunk.split("=", 1)[1])
    return pcm_bytes, sample_rate


def _cartesia_tts_sync(text: str, lang: str) -> tuple[bytes, int]:
    """Returns (pcm16_bytes, sample_rate). Cartesia Sonic: ~90ms
    time-to-first-audio, natural voice -- voice IDs pulled directly from
    this account's real /voices list (Skylar for English, Arushi -
    Hinglish Speaker, native Hindi, for Hindi)."""
    voice_id = settings.cartesia.voice_hi if lang == "hindi" else settings.cartesia.voice_en
    sample_rate = 24000
    body = json.dumps({
        "model_id": settings.cartesia.model,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": sample_rate},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.cartesia.ai/tts/bytes", data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.cartesia.api_key}",
            "Cartesia-Version": "2026-03-01",
            "User-Agent": "Sonorus/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        pcm_bytes = resp.read()
    return pcm_bytes, sample_rate


async def _run_tts(reply_lang: str, text: str) -> tuple[bytes, int]:
    """Dispatches to whichever TTS backend settings.tts.provider selects.
    Returns (pcm16_bytes, sample_rate) -- caller resamples to
    _OUT_SAMPLE_RATE if needed."""
    if settings.tts.provider == "cartesia":
        return await asyncio.to_thread(_cartesia_tts_sync, text, reply_lang)
    if settings.tts.provider == "gemini":
        return await _gemini_tts_async(text)
    voice_name = settings.tts.voice_hi if reply_lang == "hindi" else settings.tts.voice_en
    return await asyncio.to_thread(_synthesize_wav_sync, voice_name, text)


# Piper's per-voice defaults (noise_scale=0.667, noise_w=0.8) are standard
# VITS settings tuned for clarity/stability, not expressiveness -- reported
# live as sounding "too robotic" compared to Gemini's native-audio voice.
# Raising both adds real pitch/energy and rhythm variation (less flat/even
# delivery). Ceiling-setting note: this makes it sound less monotone, it
# does NOT give Piper Gemini's actual emotional range (varying tone for
# sympathy/excitement/etc. based on content) -- that requires a
# fundamentally more capable expressive TTS model, and nothing at that
# capability tier currently runs free + open-source + CPU-only at usable
# speed. This is a real improvement within Piper's ceiling, not a full fix.
_TTS_SYN_CONFIG_KWARGS = {"noise_scale": 1.0, "noise_w_scale": 1.2}


def pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
    """Wraps raw PCM16 mono samples in a WAV container -- for callers (the
    mobile app) that need a self-describing file they can hand straight to
    a standard audio player, rather than raw samples over a live socket."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buf.getvalue()


def _synthesize_wav_sync(voice_name: str, text: str) -> tuple[bytes, int]:
    """Returns (pcm16_bytes, sample_rate)."""
    from piper.config import SynthesisConfig
    voice = _get_piper_voice(voice_name)
    syn_config = SynthesisConfig(**_TTS_SYN_CONFIG_KWARGS)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)
    buf.seek(0)
    with wave.open(buf, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        pcm_bytes = wav_file.readframes(wav_file.getnframes())
    return pcm_bytes, sample_rate


def _transcribe_sync(audio_bytes: bytes) -> str:
    model = _get_stt_model()
    arr = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = model.transcribe(arr, language=None)
    return " ".join(seg.text for seg in segments).strip()


def _deepgram_transcribe_sync(audio_bytes: bytes) -> str:
    """Raw PCM16 @16kHz mono -> Deepgram's pre-recorded REST endpoint,
    matching our buffer-then-transcribe architecture (whole utterance sent
    at once, not a live stream).

    detect_language=en&detect_language=hi (multi-valued param) restricts
    the candidate set to exactly the two languages this product supports,
    instead of the unrestricted detect_language=true, which picks from
    Deepgram's full ~30+ language catalog. Confirmed live: unrestricted
    detection was misfiring on clean English audio, confidently
    transcribing it as fluent-sounding nonsense in Japanese, French, and
    Turkish (not a "detected garbage" failure -- it fully committed to the
    wrong language and produced real words in it). Restricting the
    candidate set removes those wrong languages from consideration
    entirely."""
    url = (
        f"https://api.deepgram.com/v1/listen"
        f"?model={settings.deepgram.model}&encoding=linear16&sample_rate=16000"
        f"&detect_language=en&detect_language=hi"
    )
    req = urllib.request.Request(
        url, data=audio_bytes, method="POST",
        headers={
            "Authorization": f"Token {settings.deepgram.api_key}",
            "Content-Type": "audio/raw",
            "User-Agent": "Sonorus/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    try:
        return result["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError):
        return ""


def _deepgram_transcribe_file_sync(audio_bytes: bytes, content_type: str) -> str:
    """Same as _deepgram_transcribe_sync but for a self-describing container
    file (m4a/wav/mp3) instead of raw PCM16 -- used by the mobile app,
    which records in each platform's native format rather than raw PCM
    (Android's MediaRecorder can't easily produce raw PCM/WAV without
    native code, unlike iOS). No encoding/sample_rate params: Deepgram
    auto-detects those from the container's own headers."""
    url = (
        f"https://api.deepgram.com/v1/listen"
        f"?model={settings.deepgram.model}&detect_language=en&detect_language=hi"
    )
    req = urllib.request.Request(
        url, data=audio_bytes, method="POST",
        headers={
            "Authorization": f"Token {settings.deepgram.api_key}",
            "Content-Type": content_type,
            "User-Agent": "Sonorus/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    try:
        return result["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError):
        return ""


async def _run_stt(audio_bytes: bytes) -> str:
    """Dispatches to whichever STT backend settings.stt.provider selects."""
    if settings.stt.provider == "deepgram":
        return await asyncio.to_thread(_deepgram_transcribe_sync, audio_bytes)
    return await asyncio.to_thread(_transcribe_sync, audio_bytes)


class CascadedVoiceProvider(IConversationProvider):
    """
    Fully self-hosted, free/open-source alternative to GeminiLiveProvider:
    faster-whisper (STT) -> Ollama/Llama 3.2 3B (LLM) -> Piper (TTS).

    Unlike Gemini Live, there is no persistent external session -- each
    stage is a local model call. The trade-offs (measured in Phase A, see
    the plan file): ~10-20s per-turn latency vs Gemini's ~2-5s, but $0 cost
    and no more unexplainable black-box multi-minute stalls, since every
    stage is our own inspectable code.
    """

    def __init__(self):
        self._session_id: Optional[str] = None
        self._system_prompt: str = ""
        self._messages: list[dict] = []
        self._pending_nudge: Optional[str] = None
        self._last_rms_log_time: float = 0.0

        self._audio_buffer = bytearray()
        self._is_speaking_locally = False
        self._speech_start_time: Optional[float] = None
        self._last_speech_time: Optional[float] = None

        self._is_responding = False
        self._abort_response = False
        self._audio_started = False
        self._process_lock = asyncio.Lock()

        # asyncio.create_task() only holds a WEAK reference in the event
        # loop -- a task with no other strong reference can be silently
        # garbage-collected mid-execution, no error, nothing. Confirmed
        # live: the greeting task vanished this way. Every background task
        # this provider spawns must be held here until it finishes.
        self._background_tasks: set = set()

        self._on_audio: Optional[Callable[[bytes], Awaitable[None]]] = None
        self._on_text: Optional[Callable[[str, bool], Awaitable[None]]] = None
        self._on_interruption: Optional[Callable[[], Awaitable[None]]] = None
        self._on_turn: Optional[Callable[[Optional[str]], Awaitable[None]]] = None
        self._on_user_transcript: Optional[Callable[[str], Awaitable[None]]] = None

    def _spawn(self, coro) -> None:
        """create_task, but keeps a strong reference so the task can't be
        garbage-collected before it finishes -- see the note in __init__."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    # ── Callback registration ────────────────────────────────────────

    def register_audio_handler(self, callback):
        self._on_audio = callback

    def register_text_handler(self, callback):
        self._on_text = callback

    def register_interruption_handler(self, callback):
        self._on_interruption = callback

    def register_turn_handler(self, callback):
        self._on_turn = callback

    def register_user_transcript_handler(self, callback):
        self._on_user_transcript = callback

    # ── Session lifecycle ────────────────────────────────────────────

    async def start_session(self, session_id: str, system_instruction: str, voice_name: str) -> None:
        self._session_id = session_id
        self._system_prompt = system_instruction
        self._messages = [{"role": "system", "content": system_instruction}]
        logger.info("cascaded_session_started", session_id=session_id)

    async def send_text(self, text: str) -> None:
        """Treats a text input exactly like a completed spoken utterance."""
        await self._run_turn(text)

    async def speak_opening_line(self) -> None:
        """Agent-initiated turn with no preceding user text -- for outbound
        call scenarios (e.g. loan reminder calls) where the agent must
        speak first, unlike the default inbound companion mode. Reuses
        _generate_and_speak's existing record_user_text=None bootstrap
        path (originally built for the now-removed auto-greeting) rather
        than adding a second code path for "agent speaks with no user
        turn"."""
        async with self._process_lock:
            await self._generate_and_speak(list(self._messages), record_user_text=None)

    async def _capture_callbacks(self, action) -> tuple[str, bytes, int]:
        """Shared plumbing for run_turn_and_capture / speak_opening_line_and_capture
        -- swaps in capturing callbacks for the duration of `action`, restores
        the real ones afterward, returns (reply_text, pcm_bytes, sample_rate)."""
        reply_text_holder: list[str] = []
        audio_chunks: list[bytes] = []

        prev_on_text, prev_on_audio = self._on_text, self._on_audio

        async def capture_text(text: str, is_final: bool) -> None:
            if is_final:
                reply_text_holder.append(text)

        async def capture_audio(chunk: bytes) -> None:
            audio_chunks.append(chunk)

        self._on_text = capture_text
        self._on_audio = capture_audio
        try:
            await action()
        finally:
            self._on_text, self._on_audio = prev_on_text, prev_on_audio

        reply_text = reply_text_holder[0] if reply_text_holder else ""
        pcm_bytes = b"".join(audio_chunks)
        return reply_text, pcm_bytes, _OUT_SAMPLE_RATE

    async def run_turn_and_capture(self, user_text: str) -> tuple[str, bytes, int]:
        """Runs a full turn (LLM + tools + TTS) and returns the result
        directly instead of streaming it via callbacks -- for request/
        response callers (the mobile app's push-to-talk REST endpoint)
        that don't have a persistent WebSocket to stream over."""
        return await self._capture_callbacks(lambda: self._run_turn(user_text))

    async def speak_opening_line_and_capture(self) -> tuple[str, bytes, int]:
        """Same as speak_opening_line, but returns the result instead of
        streaming it -- for the mobile app's outbound loan-call sessions."""
        return await self._capture_callbacks(self.speak_opening_line)

    async def update_system_instruction(self, instruction: str) -> None:
        # Unlike Gemini Live, the local LLM gets a fresh prompt every call --
        # this can actually take effect immediately, not just log a no-op.
        self._system_prompt = instruction
        if self._messages:
            self._messages[0] = {"role": "system", "content": instruction}

    async def send_context_nudge(self, nudge: str) -> None:
        self._pending_nudge = nudge

    async def close(self) -> None:
        self._audio_buffer.clear()
        logger.info("cascaded_session_closed", session_id=self._session_id)

    # ── Audio in: buffer + simple energy VAD for turn-boundary detection ──

    async def send_audio(self, audio_chunk: bytes) -> None:
        now = asyncio.get_event_loop().time()
        rms = _rms(audio_chunk)

        # Throttled (every ~2s) so real mic levels are visible for
        # calibration without spamming a log line per ~32ms chunk.
        if now - self._last_rms_log_time >= 2.0:
            self._last_rms_log_time = now
            logger.debug(
                "cascaded_mic_rms_sample",
                rms=round(rms, 5),
                threshold=settings.stt.vad_speech_rms_threshold,
                session_id=self._session_id,
            )

        if rms >= settings.stt.vad_speech_rms_threshold:
            if not self._is_speaking_locally:
                self._is_speaking_locally = True
                self._speech_start_time = now
            self._last_speech_time = now

            # Barge-in: real speech energy arrived while actual response
            # AUDIO is already playing. Deliberately gated on
            # self._audio_started, not just self._is_responding -- Unlike
            # Gemini (which streams audio as it generates, so something is
            # already audible within ~2-5s), this pipeline generates the
            # FULL reply (STT+LLM+TTS, ~10-20s) before sending a single
            # byte. Without this gate, any noise during that silent
            # generation window (impatience, background sound) would set
            # _abort_response before TTS even finishes, and the entire
            # freshly-generated reply gets discarded on arrival at the send
            # loop -- a fully-baked response thrown away with zero audio
            # ever played. Confirmed live: this was the actual cause of
            # "not responding" reports -- the backend WAS generating and
            # speaking real replies (visible in logs), they were just being
            # silently killed before their first byte ever reached the
            # client. Guarded also by `not self._abort_response` so this
            # fires exactly once per response, not on every subsequent
            # ~32ms mic chunk (same thrashing-loop class of bug fixed for
            # Gemini in Round 2 of the plan). Also requires
            # _BARGE_IN_MIN_DURATION_SECONDS of SUSTAINED above-threshold
            # audio (reusing _speech_start_time, set the instant this
            # speech run began) -- not a single instantaneous chunk. See
            # the constant's own comment for why: every reply was getting
            # killed within ~50-100ms of starting to speak, every time.
            #
            # Only the flag is set here -- _generate_and_speak's own send
            # loop is the sole place that calls on_interruption vs on_turn,
            # once, in order. Calling on_interruption from here too (a
            # separately spawned task, racing the loop's own on_turn call)
            # was firing both callbacks in an unpredictable order: state
            # would flip to IDLE (via on_turn) before the interruption
            # handler's own IDLE->INTERRUPTED transition ran, which isn't a
            # valid transition -- confirmed live, every single abort logged
            # "Cannot transition conversation from idle to interrupted".
            if (
                self._is_responding
                and self._audio_started
                and not self._abort_response
                and (now - self._speech_start_time) >= _BARGE_IN_MIN_DURATION_SECONDS
            ):
                self._abort_response = True

        # Only accumulate while an utterance is actually in progress (from
        # speech onset through the trailing silence-debounce window) -- not
        # during idle silence between turns, which would otherwise grow the
        # buffer unboundedly over a long session for no benefit.
        if self._is_speaking_locally:
            self._audio_buffer.extend(audio_chunk)

        if (
            self._is_speaking_locally
            and self._last_speech_time is not None
            and (now - self._last_speech_time) >= _SILENCE_DURATION_SECONDS
            and (self._last_speech_time - self._speech_start_time) >= _MIN_SPEECH_DURATION_SECONDS
        ):
            self._is_speaking_locally = False
            buffered = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            self._spawn(self._run_turn_from_audio(buffered))

    async def _run_turn_from_audio(self, audio_bytes: bytes) -> None:
        # NOTE: STT itself isn't lock-protected (it doesn't touch shared
        # response state) -- only _generate_and_speak is, see there.
        try:
            transcript = await _run_stt(audio_bytes)
        except Exception as e:
            logger.error("cascaded_stt_failed", error=str(e), session_id=self._session_id)
            return

        if not transcript.strip():
            # Previously silent -- confirmed live this can happen repeatedly
            # for over a minute straight with zero signal that anything was
            # wrong, indistinguishable from the app just not responding.
            # Whisper itself was rejecting these (visible in its own raw
            # stdout: "Compression ratio threshold is not met", "No speech
            # threshold is met") -- i.e. what got captured was noise or a
            # too-short fragment, not clean speech.
            logger.warning(
                "cascaded_stt_empty_transcript",
                audio_duration_s=round(len(audio_bytes) / 2 / 16000, 2),
                session_id=self._session_id,
            )
            return

        logger.info(
            "cascaded_stt_transcript",
            transcript=transcript,
            audio_duration_s=round(len(audio_bytes) / 2 / 16000, 2),
            session_id=self._session_id,
        )

        if self._on_user_transcript:
            await self._on_user_transcript(transcript)

        await self._run_turn(transcript)

    # ── Core turn: LLM -> TTS -> stream audio out ───────────────────────

    async def _run_turn(self, user_text: str) -> None:
        # Locked for the FULL duration (snapshot -> LLM -> TTS), not just
        # inside _generate_and_speak -- otherwise two near-simultaneous
        # callers (e.g. the greeting and a real user turn) could each take
        # a stale snapshot of self._messages before either acquires
        # anything, and/or run _generate_and_speak concurrently, corrupting
        # the shared _is_responding/_abort_response state. Confirmed live:
        # without this, the greeting and a real turn ran concurrently and
        # produced a rapid interruption-event thrashing loop.
        async with self._process_lock:
            messages = list(self._messages)
            if self._pending_nudge:
                messages.append({"role": "system", "content": self._pending_nudge})
                self._pending_nudge = None
            # KB context is injected here (not as a tool) so the LLM doesn't
            # need an extra round-trip to decide whether to search -- it's
            # already there if relevant, ignored by the system-prompt
            # instruction below if not. This is also the one place
            # guaranteed to run synchronously before the LLM call for the
            # *current* turn (see Round 7 finding: the general
            # emotion/strategy pipeline elsewhere in this app runs too late
            # to affect the turn that triggered it -- this hook doesn't
            # have that problem).
            kb_context, _category = await retrieve_kb_context(user_text)
            if kb_context:
                messages.append({"role": "system", "content": kb_context})
            messages.append({"role": "user", "content": user_text})
            await self._generate_and_speak(messages, record_user_text=user_text)

    async def _generate_and_speak(self, messages: list[dict], record_user_text: Optional[str]) -> None:
        """
        Calls the LLM with the given message list, then speaks the reply.
        Callers must hold self._process_lock for the full call.

        record_user_text: the real user utterance to persist into session
        history, or None for a bootstrap/greeting call whose synthetic
        prompt message should NOT be remembered as something the user
        actually said (only the assistant's reply gets recorded).
        """
        self._is_responding = True
        self._abort_response = False
        self._audio_started = False
        try:
            working_messages = list(messages)
            tools = all_tool_schemas()
            assistant_msg: dict = {}
            try:
                for _ in range(_MAX_TOOL_ROUNDS):
                    assistant_msg, tool_calls = await _run_llm(working_messages, tools=tools)
                    working_messages.append(assistant_msg)
                    if not tool_calls:
                        break
                    for call in tool_calls:
                        result = await execute_tool(call.name, call.arguments, self._session_id)
                        working_messages.append({
                            "role": "tool", "tool_call_id": call.id,
                            "name": call.name, "content": json.dumps(result),
                        })
            except Exception as e:
                # A malformed tool-call generation (confirmed live: Groq's
                # Llama 3.3 occasionally emits invalid function-call syntax
                # that Groq's own API then rejects with a 400
                # "tool_use_failed") previously killed the whole turn, and
                # conversation.py's shared turn-error handler (built for
                # Gemini Live's "session is broken, force a reconnect"
                # model) then closed the client connection entirely on top
                # of that -- one bad generation looked like the app going
                # offline mid-conversation. Retry once without tools: this
                # failure mode is specifically about tool-call formatting,
                # so dropping tools for the retry sidesteps it instead of
                # repeating the same failure.
                logger.warning("cascaded_llm_failed_retrying_without_tools", error=str(e), session_id=self._session_id)
                working_messages = list(messages)
                try:
                    assistant_msg, _ = await _run_llm(working_messages, tools=None)
                    working_messages.append(assistant_msg)
                except Exception as e2:
                    logger.error("cascaded_llm_failed", error=str(e2), session_id=self._session_id)
                    if self._on_turn:
                        await self._on_turn(str(e2))
                    return

            reply_text = (assistant_msg.get("content") or "").strip()

            # Persist only the messages generated THIS turn (assistant
            # replies + any tool round-trips) -- `messages` already
            # contains the prior self._messages snapshot plus the one-shot
            # nudge/KB-context, none of which should be re-appended.
            if record_user_text is not None:
                self._messages.append({"role": "user", "content": record_user_text})
            self._messages.extend(working_messages[len(messages):])

            if not reply_text:
                # Bounded loop exhausted on a tool call with no closing text
                # reply (rare) -- nothing to speak, still end the turn
                # cleanly rather than leaving the client hanging.
                if self._on_turn:
                    await self._on_turn(None)
                return

            reply_lang = detect_language(reply_text)

            try:
                pcm_bytes, src_rate = await _run_tts(reply_lang, reply_text)
            except Exception as e:
                logger.error("cascaded_tts_failed", error=str(e), session_id=self._session_id)
                if self._on_turn:
                    await self._on_turn(str(e))
                return

            pcm_bytes = _resample_pcm16(pcm_bytes, src_rate, _OUT_SAMPLE_RATE)

            # Sent right before audio starts streaming, not right after the
            # LLM reply text is ready -- previously the transcript appeared
            # on screen 1-2s before any sound, since TTS synthesis happens
            # in between. Now both land together.
            if self._on_text:
                await self._on_text(reply_text, True)

            was_aborted = False
            chunk_size = 4096
            for i in range(0, len(pcm_bytes), chunk_size):
                if self._abort_response:
                    logger.info("cascaded_response_aborted_by_barge_in", session_id=self._session_id)
                    was_aborted = True
                    break
                self._audio_started = True
                if self._on_audio:
                    await self._on_audio(pcm_bytes[i:i + chunk_size])
                await asyncio.sleep(0)

            # Interruption and normal completion are mutually exclusive
            # outcomes for a turn -- exactly one of these fires, never both,
            # and always from this single call site so there's no ordering
            # race between them (see the comment in send_audio for the bug
            # this replaced).
            if was_aborted:
                if self._on_interruption:
                    await self._on_interruption()
            elif self._on_turn:
                await self._on_turn(None)
        finally:
            self._is_responding = False
            self._abort_response = False
