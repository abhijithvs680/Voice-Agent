"""Application configuration.

All runtime configuration is read from environment variables (loaded from a
`.env` file). Using pydantic-settings gives us validation and typed access.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings sourced from the environment / `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Gemini ---
    # Accept GEMINI_API_KEY or GOOGLE_API_KEY (Pipecat's usual env name).
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    gemini_model: str = Field(
        default="models/gemini-3.1-flash-live-preview",
        validation_alias="GEMINI_MODEL",
    )
    gemini_voice_id: str = Field(default="Puck", validation_alias="GEMINI_VOICE_ID")
    primary_language: str = Field(default="EN_US", validation_alias="PRIMARY_LANGUAGE")

    # --- Twilio ---
    twilio_account_sid: str = Field(default="", validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", validation_alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(default="", validation_alias="TWILIO_PHONE_NUMBER")
    call_to_number: str = Field(default="", validation_alias="CALL_TO_NUMBER")

    # --- Server / public URL ---
    public_url: str = Field(default="", validation_alias="PUBLIC_URL")
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8888, validation_alias="PORT")

    # --- Prompt override ---
    system_prompt: Optional[str] = Field(default=None, validation_alias="SYSTEM_PROMPT")

    @property
    def resolved_gemini_key(self) -> str:
        """Return whichever Gemini key was provided."""
        return self.gemini_api_key or self.google_api_key

    @property
    def websocket_url(self) -> str:
        """Public wss:// URL that Twilio Media Streams should connect to."""
        base = self.public_url.rstrip("/")
        base = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{base}/ws"

    def require_for_call(self) -> None:
        """Validate that everything needed to place an outbound call is present."""
        missing = []
        if not self.resolved_gemini_key:
            missing.append("GEMINI_API_KEY")
        if not self.twilio_account_sid:
            missing.append("TWILIO_ACCOUNT_SID")
        if not self.twilio_auth_token:
            missing.append("TWILIO_AUTH_TOKEN")
        if not self.twilio_phone_number:
            missing.append("TWILIO_PHONE_NUMBER")
        if not self.public_url:
            missing.append("PUBLIC_URL")
        if missing:
            raise ValueError(
                "Missing required environment variables: " + ", ".join(missing)
            )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
