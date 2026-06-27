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

    # Real Libro (Phase 3)
    libro_base_url: str = "https://api.staging.libro.app"
    libro_client_id: str = ""
    libro_client_secret: str = ""
    libro_restaurant_id: str = ""

    # Voice stack
    llm_provider: str = "google"  # google | openai
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
            llm_provider=_env("YEN_LLM_PROVIDER", "google"),
            tts_provider=_env("YEN_TTS_PROVIDER", "deepgram"),
            language_mode=_env("YEN_LANGUAGE_MODE", "en"),
        )

    @property
    def is_multilingual(self) -> bool:
        return self.language_mode.lower() in ("multi", "bilingual", "fr-en", "fr+en")
