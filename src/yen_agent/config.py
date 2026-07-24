"""Environment-driven configuration for the Yen voice agent."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    # Reservation backend
    reservation_backend: str = "mock"  # mock | mock-http | libro
    restaurant_id: str = "rest_yen_mtl"
    mock_base_url: str = "http://localhost:8000"
    mock_db_path: str = ":memory:"

    # Real Libro — partner OAuth dialect (Phase 3, if ever granted)
    libro_base_url: str = "https://api.staging.libro.app"
    libro_client_id: str = ""
    libro_client_secret: str = ""
    libro_restaurant_id: str = ""

    # Real Libro — private dashboard dialect (token auth). This is the live path.
    libro_private_base_url: str = "https://api.libroreserve.com"
    libro_private_token: str = ""
    libro_private_email: str = ""
    libro_private_restaurant_id: str = "8169"  # YEN Cuisine Japonaise

    # Voice stack
    llm_provider: str = "groq"  # groq | cerebras | xai | openai | livekit | google
    llm_model: str = ""  # optional override, e.g. "gpt-4o-mini"
    tts_provider: str = "deepgram"  # deepgram | cartesia
    language_mode: str = "en"  # en | multi

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            reservation_backend=_env("YEN_RESERVATION_BACKEND", "mock"),
            restaurant_id=_env("YEN_RESTAURANT_ID", "rest_yen_mtl"),
            mock_base_url=_env("YEN_MOCK_BASE_URL", "http://localhost:8000"),
            mock_db_path=_env("YEN_MOCK_DB_PATH", ":memory:"),
            libro_base_url=_env("LIBRO_BASE_URL", "https://api.staging.libro.app"),
            libro_client_id=_env("LIBRO_CLIENT_ID"),
            libro_client_secret=_env("LIBRO_CLIENT_SECRET"),
            libro_restaurant_id=_env("LIBRO_RESTAURANT_ID") or _env("YEN_RESTAURANT_ID", "rest_yen_mtl"),
            libro_private_base_url=_env("LIBRO_PRIVATE_BASE_URL", "https://api.libroreserve.com"),
            libro_private_token=_env("LIBRO_PRIVATE_TOKEN"),
            libro_private_email=_env("LIBRO_PRIVATE_EMAIL"),
            libro_private_restaurant_id=_env("LIBRO_PRIVATE_RESTAURANT_ID", "8169"),
            llm_provider=_env("YEN_LLM_PROVIDER", "groq"),
            llm_model=_env("YEN_LLM_MODEL", ""),
            tts_provider=_env("YEN_TTS_PROVIDER", "deepgram"),
            language_mode=_env("YEN_LANGUAGE_MODE", "en"),
        )

    @property
    def is_multilingual(self) -> bool:
        return self.language_mode.lower() in ("multi", "bilingual", "fr-en", "fr+en")
