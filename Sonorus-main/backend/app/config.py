from pathlib import Path
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Resolve .env from project root (d:/Voice_Agent/.env) regardless of working directory
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE)

class DatabaseSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="DB_HOST")
    port: int = Field(default=5432, validation_alias="DB_PORT")
    user: str = Field(default="postgres", validation_alias="DB_USER")
    password: str = Field(default="postgres", validation_alias="DB_PASSWORD")
    database: str = Field(default="sonorus_db", validation_alias="DB_NAME")
    pool_size: int = Field(default=10, validation_alias="DB_POOL_SIZE")
    max_overflow: int = Field(default=20, validation_alias="DB_MAX_OVERFLOW")
    
    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

class GeminiSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    live_model: str = Field(default="gemini-2.0-flash-exp", validation_alias="GEMINI_LIVE_MODEL")
    voice_name: str = Field(default="Aoede", validation_alias="GEMINI_VOICE_NAME")  # Aoede, Charon, Fenrir, Kore, Puck
    temperature: float = Field(default=0.7, validation_alias="GEMINI_TEMPERATURE")
    # Plain text-generation model used as the cascaded pipeline's LLM stage
    # (settings.llm.provider="gemini") -- separate from live_model above,
    # which is only for the Gemini Live audio-in/audio-out API.
    text_model: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_TEXT_MODEL")
    # Dedicated text-to-speech model (settings.tts.provider="gemini") --
    # supports inline expressive tags like [cheerful]/[whispers] for real
    # emotional control, unlike Piper. Same voice_name field above is reused
    # (one multilingual voice speaks both English and Hindi, unlike Piper's
    # separate per-language voice models).
    tts_model: str = Field(default="gemini-3.1-flash-tts-preview", validation_alias="GEMINI_TTS_MODEL")
    # Embedding model for the knowledge base + (fixed, previously dead)
    # personal semantic memory -- output_dimensionality=1536 matches the
    # Vector(1536) column already in backend/app/db/schema.py.
    embedding_model: str = Field(default="gemini-embedding-001", validation_alias="GEMINI_EMBEDDING_MODEL")

class SttSettings(BaseSettings):
    # "deepgram" = Deepgram Nova-3, ~300ms latency, current default.
    # "whisper" = fully local faster-whisper, $0/offline, ~4-8s, fallback.
    provider: str = Field(default="deepgram", validation_alias="STT_PROVIDER")
    model_size: str = Field(default="small", validation_alias="STT_MODEL_SIZE")
    device: str = Field(default="cpu", validation_alias="STT_DEVICE")
    compute_type: str = Field(default="int8", validation_alias="STT_COMPUTE_TYPE")
    # Energy threshold (normalized RMS, 0-1) for the cascaded pipeline's own
    # turn-boundary VAD -- see cascaded_provider.py. Original default (0.02)
    # was only ever validated against loud synthesized test audio, never
    # real mic input; reported live as requiring near-shouting to trigger.
    # Lowered substantially and made tunable via env var so recalibrating
    # doesn't need a code change next time. Raised again from 0.006 -- real
    # mic-level logging (added after the above fix) showed this specific
    # room/mic's ambient noise floor sits at 0.003-0.009, almost exactly on
    # top of 0.006, causing constant flickering across the threshold from
    # background noise alone (confirmed live: a 43-SECOND stuck "processing
    # audio" buffer, because noise kept resetting the silence-debounce
    # timer before it could complete). Real speech in the same session
    # spiked to 0.02-0.15 -- comfortably clear of the noise floor.
    # Raised AGAIN from 0.012 -- a later session's noise floor bounced
    # 0.005-0.013, still straddling that value, producing a full minute of
    # rapid-fire false VAD triggers (~1-3s "utterances" every 1-3s, all
    # empty). This now costs real Deepgram API calls per false trigger, not
    # just wasted local CPU, so getting comfortably clear of the noise
    # floor matters more than before. 0.02 sits above both observed noise
    # ranges (0.003-0.013) while still well under real speech (0.02-0.15
    # was the low end).
    vad_speech_rms_threshold: float = Field(default=0.02, validation_alias="VAD_SPEECH_RMS_THRESHOLD")

class LlmSettings(BaseSettings):
    # "groq" = Groq-hosted open models on their custom LPU hardware --
    # current default: 394-1,000 tokens/sec, far faster than Gemini's text
    # API and Ollama's local CPU inference, at a fraction of Gemini's cost.
    # Model is Llama 3.3 70B, not the local 3B -- genuinely smarter than
    # what this laptop can run itself, not just faster.
    # "gemini" / "ollama" kept as fallbacks (see their own settings below).
    provider: str = Field(default="groq", validation_alias="LLM_PROVIDER")
    base_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_HOST")
    model: str = Field(default="llama3.2:3b", validation_alias="LLM_MODEL")

class GroqSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    model: str = Field(default="llama-3.3-70b-versatile", validation_alias="GROQ_MODEL")

class DeepgramSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="DEEPGRAM_API_KEY")
    model: str = Field(default="nova-3", validation_alias="DEEPGRAM_MODEL")

class CartesiaSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="CARTESIA_API_KEY")
    model: str = Field(default="sonic-3", validation_alias="CARTESIA_MODEL")
    # "Skylar" (multilingual-capable) and "Arushi - Hinglish Speaker"
    # (native Hindi, built for bilingual content) -- picked directly from
    # the real /voices list via this account's own API key.
    voice_en: str = Field(default="1259b7e3-cb8a-43df-9446-30971a46b8b0", validation_alias="CARTESIA_VOICE_EN")  # Devansh, Indian-accented English
    voice_hi: str = Field(default="95d51f79-c397-46f9-b49a-23763d3eaa2d", validation_alias="CARTESIA_VOICE_HI")

class TtsSettings(BaseSettings):
    # "cartesia" = Cartesia Sonic, ~90ms time-to-first-audio, natural voice
    # -- current default, the fast+expressive combination Piper and Gemini
    # TTS couldn't each deliver alone.
    # "gemini" / "piper" kept as fallbacks.
    provider: str = Field(default="cartesia", validation_alias="TTS_PROVIDER")
    voice_dir: str = Field(
        default=str(Path(__file__).resolve().parents[1] / "models" / "piper_voices"),
        validation_alias="TTS_VOICE_DIR",
    )
    # hfc_female is trained on conversational speech, not audiobook-style
    # narration like lessac -- picked after lessac was reported to sound
    # completely flat/robotic even with expressiveness tuning pushed up.
    voice_en: str = Field(default="en_US-hfc_female-medium", validation_alias="TTS_VOICE_EN")
    voice_hi: str = Field(default="hi_IN-pratham-medium", validation_alias="TTS_VOICE_HI")

class PersonaSettings(BaseSettings):
    name: str = Field(default="Sonorus", validation_alias="PERSONA_NAME")
    traits: List[str] = [
        "warm", 
        "curious", 
        "patient", 
        "emotionally intelligent", 
        "conversational", 
        "thoughtful human friend"
    ]
    description: str = (
        "A warm and curious human conversational companion. Sonorus speaks naturally, "
        "avoids academic lectures, doesn't use bullet points, and shows genuine Interest in the user's life."
    )

class AuthSettings(BaseSettings):
    # Signs mobile-app user session tokens (HMAC-SHA256, stdlib-only --
    # see services/auth.py). Real per-deployment secret lives in .env.
    jwt_secret: str = Field(default="dev-insecure-secret-change-me", validation_alias="JWT_SECRET")
    token_expire_days: int = Field(default=30, validation_alias="JWT_EXPIRE_DAYS")
    # Web application OAuth client ID from Google Cloud Console -- verifies
    # that a Google ID token was actually issued for this app (the
    # "audience" claim) before trusting it.
    google_client_id: str = Field(default="", validation_alias="GOOGLE_CLIENT_ID")

class ResendSettings(BaseSettings):
    api_key: str = Field(default="", validation_alias="RESEND_API_KEY")
    from_email: str = Field(default="onboarding@resend.dev", validation_alias="RESEND_FROM_EMAIL")

class AdminSettings(BaseSettings):
    # Single shared internal-admin credential (not per-user) -- was
    # previously hardcoded in main.py, silently ignoring these env vars
    # entirely. Now actually wired up so rotating the password is a .env
    # change, not a code change.
    username: str = Field(default="admin", validation_alias="ADMIN_USERNAME")
    password: str = Field(default="", validation_alias="ADMIN_PASSWORD")

class ServerSettings(BaseSettings):
    host: str = Field(default="127.0.0.1", validation_alias="SERVER_HOST")
    port: int = Field(default=8000, validation_alias="SERVER_PORT")
    debug: bool = Field(default=True, validation_alias="SERVER_DEBUG")
    # Publicly reachable base URL for this deployment -- used to build
    # links (e.g. the email-verification link) that need to work from
    # outside this server, not just internally.
    public_base_url: str = Field(default="http://localhost:8000", validation_alias="PUBLIC_BASE_URL")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    server: ServerSettings = Field(default_factory=ServerSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    persona: PersonaSettings = Field(default_factory=PersonaSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)
    resend: ResendSettings = Field(default_factory=ResendSettings)
    use_in_memory_cache: bool = Field(default=True, validation_alias="USE_IN_MEMORY_CACHE")

settings = Settings()
