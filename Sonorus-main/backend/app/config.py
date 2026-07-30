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

class ServerSettings(BaseSettings):
    host: str = Field(default="127.0.0.1", validation_alias="SERVER_HOST")
    port: int = Field(default=8000, validation_alias="SERVER_PORT")
    debug: bool = Field(default=True, validation_alias="SERVER_DEBUG")

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
    use_in_memory_cache: bool = Field(default=True, validation_alias="USE_IN_MEMORY_CACHE")

settings = Settings()
