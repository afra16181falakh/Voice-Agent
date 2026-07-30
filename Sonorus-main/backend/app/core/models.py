from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

# ==========================================
# Enums
# ==========================================

class ConversationState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    SILENCE = "silence"
    ENDING = "ending"

class EmotionType(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    FRUSTRATED = "frustrated"
    ANXIOUS = "anxious"
    EXCITED = "excited"
    CONFUSED = "confused"
    BORED = "bored"
    ENGAGED = "engaged"
    TIRED = "tired"
    REFLECTIVE = "reflective"
    PLAYFUL = "playful"

class StrategyType(str, Enum):
    LISTEN = "listen"
    COMFORT = "comfort"
    ENCOURAGE = "encourage"
    EXPLAIN = "explain"
    ASK_QUESTION = "ask_question"
    CHANGE_TOPIC = "change_topic"
    REMAIN_SILENT = "remain_silent"
    ACKNOWLEDGE = "acknowledge"
    EMPATHIZE = "empathize"
    MAKE_JOKE = "make_joke"
    CONTINUE_TOPIC = "continue_topic"
    CLARIFY = "clarify"

class UserIntent(str, Enum):
    SHARE_INFORMATION = "share_information"
    ASK_QUESTION = "ask_question"
    SEEK_SUPPORT = "seek_support"
    MAKE_JOKE = "make_joke"
    CHANGE_TOPIC = "change_topic"
    CONFIRM = "confirm"
    DENY = "deny"
    UNCLEAR = "unclear"
    FAREWELL = "farewell"
    RESUME = "resume"
    GREETING = "greeting"

class MemoryType(str, Enum):
    SHORT_TERM = "short_term"
    CONVERSATION_HISTORY = "conversation_history"
    LONG_TERM_FACT = "long_term_fact"
    PREFERENCE = "preference"
    PERSONAL_INFO = "personal_info"
    SEMANTIC = "semantic"
    TOPIC = "topic"
    SUMMARY = "summary"

# ==========================================
# Domain Models
# ==========================================

class AudioChunk(BaseModel):
    data: bytes
    format: str = "pcm"
    sample_rate: int = 16000
    channels: int = 1

class Speaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class TranscriptSegment(BaseModel):
    speaker: Speaker
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_final: bool = True

class EmotionState(BaseModel):
    emotion: EmotionType
    confidence: float = 1.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class EmotionTimeline(BaseModel):
    states: List[EmotionState] = Field(default_factory=list)
    current_trend: str = "stable"

class StrategyDecision(BaseModel):
    strategy: StrategyType
    reasoning: str
    target_pacing: str = "normal"  # normal, slow, fast, excited, empathetic
    injected_backchannel: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class MemoryItem(BaseModel):
    id: Optional[str] = None
    memory_type: MemoryType
    key: str
    value: str
    embedding: Optional[List[float]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class TopicState(BaseModel):
    current_topic: str = "general"
    previous_topics: List[str] = Field(default_factory=list)
    depth: int = 0
    sentiment: str = "neutral"

class ConversationContext(BaseModel):
    session_id: str
    language: str = "english"
    detected_emotion: EmotionType = EmotionType.NEUTRAL
    emotion_history: List[EmotionState] = Field(default_factory=list)
    selected_strategy: Optional[StrategyDecision] = None
    current_topic: TopicState = Field(default_factory=TopicState)
    user_intent: UserIntent = UserIntent.SHARE_INFORMATION
    relevant_memories: List[MemoryItem] = Field(default_factory=list)
    short_term_history: List[TranscriptSegment] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class SessionInfo(BaseModel):
    session_id: str
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
