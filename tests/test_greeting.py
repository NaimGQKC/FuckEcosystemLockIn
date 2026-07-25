"""The greeting, the AI disclosure, barge-in, and the telemetry behind them.

Context: 16 of 84 real calls (19%) ended with the caller never speaking a word
(docs/GREETING_ABANDONMENT.md). We cannot test on real users, so these tests
pin the properties we *can* verify without a phone line: the greeting is short
and French-first, the disclosure is never silently dropped, barge-in is not
disabled by the SDK's defaults, and every number the reporting prints was
actually measured.
"""

from __future__ import annotations

import pytest

from yen_agent import prompts
from yen_agent.config import Settings
from yen_agent.prompts import (
    DISCLOSURE_EN,
    DISCLOSURE_FR,
    GREETING_EN,
    GREETING_FR,
    disclosure_reminder,
    greeting_for,
    system_instructions,
)

#: Deepgram Aura-2 runs around 3 words/second in normal speech. The owner's
#: bound is "under ~1.5 seconds spoken", so 4 words is the ceiling for the
#: greeting itself. This is an ASSUMPTION, deliberately conservative, and it is
#: the thing to re-derive from `calls.greeting_ms` once the line is live.
WORDS_PER_SECOND = 3.0
GREETING_BUDGET_S = 1.5
DISCLOSURE_BUDGET_S = 2.0


def _spoken_seconds(text: str) -> float:
    return len(text.split()) / WORDS_PER_SECOND


# --------------------------------------------------------------------------
# 1. The greeting is short, and French comes first
# --------------------------------------------------------------------------


def test_greeting_is_under_the_spoken_budget():
    """The old greeting was 14 words; a padded one once ran 13 seconds."""
    for greeting in (GREETING_FR, GREETING_EN):
        assert _spoken_seconds(greeting) <= GREETING_BUDGET_S, greeting


def test_disclosure_clause_is_also_short():
    for clause in (DISCLOSURE_FR, DISCLOSURE_EN):
        assert _spoken_seconds(clause) <= DISCLOSURE_BUDGET_S, clause


def test_multilingual_mode_greets_in_french_first():
    """Two-thirds of this venue's calls are French. English loses them at hello."""
    greeting, disclosure = greeting_for(multilingual=True)
    assert greeting == GREETING_FR
    assert disclosure == DISCLOSURE_FR
    assert "bonjour" in greeting.lower()


def test_english_only_mode_still_greets_in_english():
    greeting, disclosure = greeting_for(multilingual=False)
    assert (greeting, disclosure) == (GREETING_EN, DISCLOSURE_EN)


def test_greeting_is_not_bilingual():
    """Saying it twice makes it longer, which is the defect we're fixing."""
    fr, _ = greeting_for(multilingual=True)
    assert "hello" not in fr.lower()
    assert "how can i help" not in fr.lower()


def test_greeting_names_the_restaurant_first():
    """The caller must know who answered before anything else."""
    for greeting in (GREETING_FR, GREETING_EN):
        assert greeting.upper().startswith("YEN")


def test_greeting_carries_no_disclosure_text():
    """Disclosure is a separate, interruptible utterance — not first-breath cost."""
    for greeting in (GREETING_FR, GREETING_EN):
        low = greeting.lower()
        assert "assistant" not in low
        assert " ia" not in low and "ai " not in low


# --------------------------------------------------------------------------
# 2. Disclosure is deferred, never dropped
# --------------------------------------------------------------------------


def test_disclosure_actually_discloses():
    assert "assistant" in DISCLOSURE_FR.lower()
    assert "virtuel" in DISCLOSURE_FR.lower()
    assert "ai assistant" in DISCLOSURE_EN.lower()


def test_disclosure_reminder_exists_for_both_languages():
    for multilingual in (True, False):
        note = disclosure_reminder(multilingual)
        assert "Disclosure not yet heard" in note
        assert "first" in note.lower()


def test_reminder_appended_to_instructions_is_still_valid_prompt():
    base = system_instructions(multilingual=True, today="2026-07-25")
    combined = base + disclosure_reminder(True)
    assert combined.startswith(base)
    assert "Disclosure not yet heard" in combined


def test_base_prompt_tells_the_model_not_to_re_disclose_by_default():
    base = system_instructions(multilingual=True, today="2026-07-25")
    assert "Disclosure not yet heard" in base  # the escape hatch is referenced
    assert "do NOT repeat it" in base


# --------------------------------------------------------------------------
# 3. Barge-in during the greeting
# --------------------------------------------------------------------------


def test_aec_warmup_defaults_to_disabled():
    """THE barge-in fix.

    livekit-agents defaults ``aec_warmup_duration=3.0``, and during that window
    it blocks interruption AND pushes silence to the STT — so a caller cannot
    talk over the greeting and their first words are never transcribed. Our
    greeting is ~1s, so the SDK default covers all of it.
    """
    assert Settings().aec_warmup_s == 0.0


def test_aec_warmup_is_env_overridable_and_typo_safe(monkeypatch):
    monkeypatch.setenv("YEN_AEC_WARMUP_S", "0.4")
    assert Settings.from_env().aec_warmup_s == pytest.approx(0.4)
    monkeypatch.setenv("YEN_AEC_WARMUP_S", "not-a-number")
    assert Settings.from_env().aec_warmup_s == 0.0  # must never break the phone


def test_sdk_still_gates_barge_in_on_aec_warmup():
    """Regression alarm on the SDK behaviour our fix depends on.

    If a future livekit-agents stops disabling interruptions during AEC warmup,
    this fails and we can drop the override instead of carrying it forever.
    """
    livekit_agents = pytest.importorskip("livekit.agents")
    import inspect

    from livekit.agents.voice import agent_activity

    src = inspect.getsource(agent_activity.AgentActivity._interrupt_by_audio_activity)
    assert "_aec_warmup_remaining" in src, (
        "livekit-agents no longer gates interruption on AEC warmup — re-check "
        "whether Settings.aec_warmup_s is still needed."
    )
    assert livekit_agents  # keep the importorskip binding meaningful


def test_sdk_say_still_accepts_allow_interruptions():
    """`say(allow_interruptions=True)` is necessary (but was not sufficient)."""
    pytest.importorskip("livekit.agents")
    import inspect

    from livekit.agents import AgentSession

    assert "allow_interruptions" in inspect.signature(AgentSession.say).parameters


# --------------------------------------------------------------------------
# 4. The greeting sequence itself (fake session — no audio, no room)
# --------------------------------------------------------------------------


class _FakeHandle:
    def __init__(self, interrupted: bool):
        self.interrupted = interrupted

    async def wait_for_playout(self):
        return None


class _FakeSession:
    """Just enough AgentSession to exercise the greeting flow."""

    def __init__(self, interrupt_on: set[int] | None = None):
        self.said: list[tuple[str, bool]] = []
        self._interrupt_on = interrupt_on or set()

    def say(self, text, *, allow_interruptions=False, **kw):
        self.said.append((text, allow_interruptions))
        return _FakeHandle(len(self.said) - 1 in self._interrupt_on)


class _FakeAgent:
    def __init__(self):
        self.instructions = "BASE"

    def update_instructions(self, instructions: str) -> None:
        self.instructions = instructions


@pytest.fixture
def greeting_mod():
    return pytest.importorskip("yen_agent.agent")


async def test_uninterrupted_call_hears_greeting_then_disclosure(greeting_mod):
    session, agent = _FakeSession(), _FakeAgent()
    tele = greeting_mod.GreetingTelemetry()
    tele.mark_answered()
    tele.mark_agent_speaking()

    await greeting_mod._speak_greeting(
        session, agent, Settings(language_mode="multi"), tele, "BASE"
    )

    assert [t for t, _ in session.said] == [GREETING_FR, DISCLOSURE_FR]
    assert all(allow for _, allow in session.said), "both utterances must be interruptible"
    assert tele.disclosure_spoken is True
    assert tele.greeting_interrupted is False
    assert agent.instructions == "BASE"  # no reminder needed


async def test_barge_in_on_the_greeting_skips_the_disclosure_and_defers_it(greeting_mod):
    """We do not talk over a caller to read them a compliance line."""
    session, agent = _FakeSession(interrupt_on={0}), _FakeAgent()
    tele = greeting_mod.GreetingTelemetry()
    tele.mark_answered()

    await greeting_mod._speak_greeting(
        session, agent, Settings(language_mode="multi"), tele, "BASE"
    )

    assert [t for t, _ in session.said] == [GREETING_FR]
    assert tele.greeting_interrupted is True
    assert tele.disclosure_spoken is False
    # Deferred, not dropped:
    assert "Disclosure not yet heard" in agent.instructions
    assert agent.instructions.startswith("BASE")


async def test_barge_in_during_the_disclosure_also_defers_it(greeting_mod):
    session, agent = _FakeSession(interrupt_on={1}), _FakeAgent()
    tele = greeting_mod.GreetingTelemetry()
    tele.mark_answered()

    await greeting_mod._speak_greeting(
        session, agent, Settings(language_mode="multi"), tele, "BASE"
    )

    assert len(session.said) == 2
    assert tele.disclosure_spoken is False
    assert "Disclosure not yet heard" in agent.instructions


async def test_english_mode_speaks_the_english_pair(greeting_mod):
    session, agent = _FakeSession(), _FakeAgent()
    tele = greeting_mod.GreetingTelemetry()
    tele.mark_answered()
    await greeting_mod._speak_greeting(session, agent, Settings(), tele, "BASE")
    assert [t for t, _ in session.said] == [GREETING_EN, DISCLOSURE_EN]


# --------------------------------------------------------------------------
# 5. A French greeting needs a voice that can pronounce French
# --------------------------------------------------------------------------


def test_deepgram_voices_are_english_only():
    """Documents WHY multilingual mode does not use the Deepgram voice.

    If Deepgram ever ships a French Aura voice this fails, and we can collapse
    back to a single vendor.
    """
    pytest.importorskip("livekit.plugins.deepgram")
    import typing

    from livekit.plugins.deepgram.models import TTSModels

    assert all(m.endswith("-en") for m in typing.get_args(TTSModels))


def test_multilingual_tts_is_not_the_english_only_voice(monkeypatch):
    agent_mod = pytest.importorskip("yen_agent.agent")
    monkeypatch.setenv("LIVEKIT_API_KEY", "fake")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "fake")
    monkeypatch.setenv("LIVEKIT_URL", "wss://fake.livekit.cloud")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake")

    tts = agent_mod._build_tts(Settings(language_mode="multi"))
    assert "deepgram" not in type(tts).__module__


def test_english_mode_keeps_the_single_vendor_deepgram_voice(monkeypatch):
    agent_mod = pytest.importorskip("yen_agent.agent")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake")
    tts = agent_mod._build_tts(Settings())
    assert "deepgram" in type(tts).__module__


def test_tts_model_env_override_wins(monkeypatch):
    agent_mod = pytest.importorskip("yen_agent.agent")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake")
    tts = agent_mod._build_tts(Settings(language_mode="multi", tts_model="aura-2-thalia-en"))
    assert "deepgram" in type(tts).__module__


def test_multilingual_without_livekit_credentials_warns_loudly(monkeypatch, caplog):
    """Falling back to an English voice for a French greeting must not be quiet."""
    agent_mod = pytest.importorskip("yen_agent.agent")
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake")

    with caplog.at_level("WARNING", logger="yen-agent"):
        agent_mod._build_tts(Settings(language_mode="multi"))
    assert any("mispronounced" in r.message % r.args if r.args else "mispronounced" in r.message
               for r in caplog.records)


def test_prompts_module_documents_the_disclosure_tradeoff():
    """The decision must survive in the code, not just in a review comment."""
    import inspect

    src = inspect.getsource(prompts)
    assert "tradeoff" in src.lower()
    assert "Deferred, never dropped." in src or "deferred, never dropped" in src.lower()
