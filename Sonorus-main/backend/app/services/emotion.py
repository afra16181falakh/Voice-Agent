import re
import structlog
from collections import deque
from datetime import datetime
from typing import Dict, Deque, List

from app.core.interfaces.emotion import IEmotionEngine
from app.core.models import (
    EmotionType, EmotionState, EmotionTimeline
)

logger = structlog.get_logger(__name__)

# Max emotion states remembered per session
MAX_EMOTION_HISTORY = 20

# ──────────────────────────────────────────────────────────
# Keyword-based emotion classifier (fast, zero-latency, no API)
# In a future iteration this could be replaced with an embedding
# model or a Gemini call, but rules keep it sub-millisecond.
# ──────────────────────────────────────────────────────────

_EMOTION_KEYWORDS: Dict[EmotionType, List[str]] = {
    EmotionType.HAPPY: [
        "happy", "great", "wonderful", "amazing", "love", "fantastic",
        "excellent", "joy", "delighted", "brilliant", "yay", "awesome",
        "thrilled", "pleased", "glad", "😊", "😄", "🎉",
        # Hindi / Hinglish
        "khush", "mast", "zabardast", "bahut acha", "ekdum badhiya",
        "shukriya", "maja aa gaya", "kya baat", "wah",
    ],
    EmotionType.SAD: [
        "sad", "unhappy", "depressed", "miss", "loss", "grief", "cry",
        "tears", "heartbreak", "alone", "lonely", "hurt", "pain",
        "unfortunately", "regret", "sorrow", "😢", "😔",
        # Hindi / Hinglish
        "dukhi", "rona", "bura lag raha", "dil dukha", "udaas",
        "tanha", "akela", "dard", "takleef",
    ],
    EmotionType.FRUSTRATED: [
        "frustrated", "annoyed", "irritated", "angry", "hate", "stupid",
        "useless", "ridiculous", "terrible", "awful", "ugh", "argh",
        "can't", "won't", "doesn't work", "😠", "😤",
        # Hindi / Hinglish
        "gussa", "pareshaan", "naraaz", "tang aa gaya", "bore ho gaya",
        "kya bakwaas", "bekaar", "nahi ho raha", "bahut bura",
    ],
    EmotionType.ANXIOUS: [
        "worried", "anxious", "nervous", "stress", "scared", "fear",
        "panic", "overwhelmed", "tense", "uneasy", "unsure", "doubt",
        "uncertain", "afraid", "dread", "😰", "😟",
        # Hindi / Hinglish
        "darr", "ghabra", "tension", "chinta", "dar lag raha",
        "bahut tension hai", "kya hoga", "samajh nahi aa raha",
    ],
    EmotionType.EXCITED: [
        "excited", "can't wait", "thrilling", "wow", "omg", "oh my",
        "unbelievable", "incredible", "electric", "buzz", "eager",
        "pumped", "fired up", "yes!", "🤩", "🔥",
        # Hindi / Hinglish
        "itna excited", "kya scene hai", "yaar sun", "full on",
        "ekdum ready", "kal se shuru",
    ],
    EmotionType.CONFUSED: [
        "confused", "don't understand", "what do you mean", "unclear",
        "huh", "lost", "make sense", "explain", "why", "how come",
        "not sure", "?", "🤔",
        # Hindi / Hinglish
        "samajh nahi aaya", "matlab?", "kya matlab", "thoda explain",
        "ye kya hai", "ajeeb", "soch raha hoon",
    ],
    EmotionType.TIRED: [
        "tired", "exhausted", "sleepy", "drained", "worn out", "fatigue",
        "lethargic", "yawn", "need sleep", "can't focus", "long day", "😴",
        # Hindi / Hinglish
        "thak gaya", "thak gayi", "neend aa rahi", "bahut thaka hoon",
        "aaj bahut kaam tha", "sar dard",
    ],
    EmotionType.REFLECTIVE: [
        "thinking about", "realized", "looking back", "remember when",
        "used to", "i've been wondering", "it made me think", "reminds me",
        "in hindsight", "reflect", "wonder", "pondering",
        # Hindi / Hinglish
        "soch raha tha", "yaad aaya", "pehle aisa tha", "kya hota agar",
        "mujhe lag raha hai",
    ],
    EmotionType.PLAYFUL: [
        "haha", "lol", "funny", "joke", "kidding", "just playing",
        "teasing", "😂", "😜", "🤣", "wink",
        # Hindi / Hinglish
        "hahaha", "yaar mazaak kar raha", "chill kar", "timepass",
        "ekdum comedy", "teri toh", "pagal hai kya",
    ],
    EmotionType.ENGAGED: [
        "tell me more", "interesting", "keep going", "really?", "wow",
        "that's fascinating", "go on", "i'm listening", "absolutely",
        "of course", "great point",
        # Hindi / Hinglish
        "aur batao", "sach mein?", "woh toh sahi hai", "bata na",
        "haan haan", "phir kya hua",
    ],
    EmotionType.BORED: [
        "boring", "bored", "whatever", "meh", "not really", "i guess",
        "don't care", "doesn't matter", "anyway", "never mind",
        # Hindi / Hinglish
        "kuch nahi", "bakwaas hai", "chodo yaar", "koi baat nahi",
        "same old", "kuch naya nahi",
    ],
}


def _detect_emotion_from_keywords(text: str) -> EmotionType:
    """Returns the best-matched EmotionType using keyword scoring."""
    text_lower = text.lower()
    scores: Dict[EmotionType, int] = {}

    for emotion, keywords in _EMOTION_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count:
            scores[emotion] = count

    if not scores:
        return EmotionType.NEUTRAL

    return max(scores, key=lambda e: scores[e])


def _calculate_trend(states: List[EmotionState]) -> str:
    """Derives a coarse trend label from recent emotion history."""
    if len(states) < 3:
        return "stable"

    positive = {EmotionType.HAPPY, EmotionType.EXCITED, EmotionType.PLAYFUL, EmotionType.ENGAGED}
    negative = {EmotionType.SAD, EmotionType.FRUSTRATED, EmotionType.ANXIOUS, EmotionType.TIRED, EmotionType.BORED}

    recent = [s.emotion for s in states[-5:]]
    pos_count = sum(1 for e in recent if e in positive)
    neg_count = sum(1 for e in recent if e in negative)

    if pos_count > neg_count + 1:
        return "improving"
    if neg_count > pos_count + 1:
        return "declining"
    return "stable"


class EmotionEngine(IEmotionEngine):
    """
    Fast, rule-based emotion tracker. Analyzes each user utterance via
    keyword scoring and maintains a rolling timeline per session.
    """

    def __init__(self):
        self._timelines: Dict[str, Deque[EmotionState]] = {}

    def _get_timeline_deque(self, session_id: str) -> Deque[EmotionState]:
        if session_id not in self._timelines:
            self._timelines[session_id] = deque(maxlen=MAX_EMOTION_HISTORY)
        return self._timelines[session_id]

    async def analyze_utterance(self, session_id: str, text: str) -> EmotionState:
        """Detects the emotion in a single utterance and appends it to the session timeline."""
        emotion_type = _detect_emotion_from_keywords(text)

        # Confidence heuristic: longer text + more matched keywords = higher confidence
        word_count = len(text.split())
        confidence = min(0.95, 0.5 + (word_count / 40))

        state = EmotionState(
            emotion=emotion_type,
            confidence=round(confidence, 2),
            timestamp=datetime.utcnow()
        )

        self._get_timeline_deque(session_id).append(state)
        logger.debug(
            "emotion_detected",
            emotion=emotion_type.value,
            confidence=state.confidence,
            session_id=session_id
        )
        return state

    async def get_timeline(self, session_id: str) -> EmotionTimeline:
        """Returns the full emotion timeline with trend annotation."""
        states = list(self._get_timeline_deque(session_id))
        trend = _calculate_trend(states)
        return EmotionTimeline(states=states, current_trend=trend)

    async def get_current_emotion(self, session_id: str) -> EmotionType:
        """Returns the most recent detected emotion, defaulting to NEUTRAL."""
        dq = self._get_timeline_deque(session_id)
        if dq:
            return dq[-1].emotion
        return EmotionType.NEUTRAL

    async def clear_timeline(self, session_id: str) -> None:
        """Clears the session's emotion timeline."""
        self._timelines.pop(session_id, None)
