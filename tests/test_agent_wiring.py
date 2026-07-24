"""Wiring tests against the real livekit-agents SDK.

These run only when the `[agent]` extras are installed (pytest.importorskip
otherwise), and use fake keys — constructors validate configuration shape, not
credentials. They catch SDK API drift (renamed kwargs, deprecated options,
missing plugins) without needing audio or cloud access.
"""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("livekit.agents")


@pytest.fixture(autouse=True)
def fake_keys(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake")
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    monkeypatch.setenv("CARTESIA_API_KEY", "fake")


def _build_session(settings, with_livekit_creds: bool, monkeypatch):
    if with_livekit_creds:
        monkeypatch.setenv("LIVEKIT_API_KEY", "fake")
        monkeypatch.setenv("LIVEKIT_API_SECRET", "fake")
        monkeypatch.setenv("LIVEKIT_URL", "wss://fake.livekit.cloud")
    else:
        monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
        monkeypatch.delenv("LIVEKIT_URL", raising=False)

    from livekit.agents import AgentSession

    from yen_agent.agent import _build_llm, _build_stt, _build_tts, _build_turn_handling

    return AgentSession(
        stt=_build_stt(settings),
        llm=_build_llm(settings),
        tts=_build_tts(settings),
        turn_handling=_build_turn_handling(settings),
    )


def test_english_session_constructs_without_deprecations(monkeypatch):
    from yen_agent.config import Settings

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        _build_session(Settings(), with_livekit_creds=True, monkeypatch=monkeypatch)


def test_console_mode_without_livekit_creds_falls_back_to_vad(monkeypatch):
    from yen_agent.agent import _build_turn_handling
    from yen_agent.config import Settings

    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    opts = _build_turn_handling(Settings())
    assert "turn_detection" not in opts  # VAD fallback, no crash at call time


def test_multilingual_cartesia_session_constructs(monkeypatch):
    from yen_agent.config import Settings

    _build_session(
        Settings(language_mode="multi", tts_provider="cartesia"),
        with_livekit_creds=True,
        monkeypatch=monkeypatch,
    )


def test_agent_registers_all_seven_tools():
    from yen_agent.concierge import Concierge
    from yen_agent.prompts import system_instructions
    from yen_agent.reservation.mock import MockReservationService
    from yen_agent.tools import ReservationAgent

    svc = MockReservationService.in_process(db_path=":memory:")
    agent = ReservationAgent(
        Concierge(svc),
        instructions=system_instructions(multilingual=False, today="2026-07-24"),
    )
    assert len(agent.tools) == 7


def test_noise_cancellation_plugin_installed():
    from livekit.plugins import noise_cancellation

    assert hasattr(noise_cancellation, "BVC")
