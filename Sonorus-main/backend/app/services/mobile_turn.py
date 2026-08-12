"""Lightweight REST turn-taking for the mobile (push-to-talk) app --
separate from the WebSocket-based ConversationManager/SpeechGateway path
the web app uses, since a REST request/response cycle per turn doesn't
need a persistent connection or the state-machine/telemetry plumbing built
for continuous streaming. Reuses CascadedVoiceProvider directly (the same
STT/LLM/tools/TTS pipeline), just driven synchronously per HTTP call."""
import json
import uuid
import structlog
from datetime import datetime
from sqlalchemy import select

from app.config import settings
from app.db.connection import async_session_maker
from app.db.schema import CallHistoryORM
from app.services.cascaded_provider import CascadedVoiceProvider, _deepgram_transcribe_file_sync, pcm16_to_wav_bytes
from app.services.prompt import PromptBuilder
from app.services.loan_data import get_customer

logger = structlog.get_logger(__name__)

_sessions: dict[str, CascadedVoiceProvider] = {}
_prompt_builder = PromptBuilder()


async def create_mobile_session(call_type: str | None, customer_id: str | None, user_id: str) -> tuple[str, str, bytes]:
    """Returns (session_id, opening_text, opening_wav_bytes) -- opening
    text/audio are empty unless this is an outbound loan-reminder session,
    where the agent speaks first."""
    session_id = str(uuid.uuid4())
    provider = CascadedVoiceProvider()

    customer = get_customer(customer_id) if (call_type == "loan_reminder" and customer_id) else None
    prompt = _prompt_builder.build_loan_reminder_prompt(customer) if customer else _prompt_builder.build_initial_prompt()

    await provider.start_session(session_id, prompt, settings.tts.voice_en)
    _sessions[session_id] = provider

    opening_text, opening_wav = "", b""
    if customer:
        text, pcm, rate = await provider.speak_opening_line_and_capture()
        opening_text = text
        opening_wav = pcm16_to_wav_bytes(pcm, rate) if pcm else b""

    try:
        async with async_session_maker() as db:
            entries = [{"role": "agent", "text": opening_text}] if opening_text else []
            db.add(CallHistoryORM(
                id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                call_type=call_type,
                customer_name=customer.name if customer else None,
                transcript_json=json.dumps(entries),
            ))
            await db.commit()
    except Exception as e:
        logger.warning("call_history_create_failed", error=str(e), session_id=session_id)

    return session_id, opening_text, opening_wav


async def run_mobile_turn(session_id: str, audio_bytes: bytes, content_type: str) -> tuple[str, str, bytes]:
    """Returns (user_transcript, reply_text, wav_bytes)."""
    provider = _sessions.get(session_id)
    if provider is None:
        raise KeyError(session_id)

    import asyncio
    transcript = await asyncio.to_thread(_deepgram_transcribe_file_sync, audio_bytes, content_type)
    if not transcript.strip():
        return "", "", b""

    reply_text, pcm_bytes, sample_rate = await provider.run_turn_and_capture(transcript)
    wav_bytes = pcm16_to_wav_bytes(pcm_bytes, sample_rate) if pcm_bytes else b""

    try:
        async with async_session_maker() as db:
            result = await db.execute(select(CallHistoryORM).where(CallHistoryORM.session_id == session_id))
            row = result.scalar_one_or_none()
            if row:
                entries = json.loads(row.transcript_json)
                entries.append({"role": "user", "text": transcript})
                entries.append({"role": "agent", "text": reply_text})
                row.transcript_json = json.dumps(entries)
                await db.commit()
    except Exception as e:
        logger.warning("call_history_append_failed", error=str(e), session_id=session_id)

    return transcript, reply_text, wav_bytes


async def end_mobile_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    try:
        async with async_session_maker() as db:
            result = await db.execute(select(CallHistoryORM).where(CallHistoryORM.session_id == session_id))
            row = result.scalar_one_or_none()
            if row and row.ended_at is None:
                row.ended_at = datetime.utcnow()
                await db.commit()
    except Exception as e:
        logger.warning("call_history_end_failed", error=str(e), session_id=session_id)


async def list_call_history(user_id: str, limit: int = 30) -> list[dict]:
    async with async_session_maker() as db:
        result = await db.execute(
            select(CallHistoryORM)
            .where(CallHistoryORM.user_id == user_id)
            .order_by(CallHistoryORM.started_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
    return [
        {
            "session_id": r.session_id,
            "call_type": r.call_type,
            "customer_name": r.customer_name,
            "transcript": json.loads(r.transcript_json),
            "started_at": r.started_at.isoformat(),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        }
        for r in rows
    ]
