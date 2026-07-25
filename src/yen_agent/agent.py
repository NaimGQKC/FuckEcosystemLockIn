"""LiveKit Agents entrypoint and voice-stack wiring for the Yen agent.

Run modes (after `pip install -e ".[agent]"` and filling in `.env`):

    python -m yen_agent.agent console   # local terminal audio, no server
    python -m yen_agent.agent dev       # connect to LiveKit Cloud + browser test

The reservation backend is chosen by env (`YEN_RESERVATION_BACKEND`), defaulting
to the in-process mock — so this runs end-to-end with no Libro credentials.

Structure follows LiveKit's recommended patterns: bundled VAD, metrics + usage
collection, hosted semantic turn detection, telephony noise cancellation, and
the current date injected into the prompt so relative dates ("this Friday")
resolve correctly. Compatible with livekit-agents >= 1.6.4.

Model identifiers below are the recommended low-cost stack. Plugin model names
occasionally change between releases; verify them against the installed plugin
version if a model isn't found.
"""

from __future__ import annotations

import datetime as dt
import logging

import os

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    RoomInputOptions,
    TurnHandlingOptions,
    WorkerOptions,
    cli,
    metrics,
)
# Plugins MUST be imported at module top level: LiveKit registers each plugin at
# import time and requires that to happen on the main thread. Importing them
# lazily inside a builder (which runs in the job worker thread) raises
# "Plugins must be registered on the main thread". deepgram/google/openai ship
# with the [agent] extra; noise_cancellation is optional.
from livekit.plugins import deepgram, google, openai

try:
    from livekit.plugins import noise_cancellation
except Exception:  # pragma: no cover - optional plugin
    noise_cancellation = None

from .concierge import Concierge
from .config import Settings
from .prompts import GREETING_EN, GREETING_FR, system_instructions
from .reservation import build_service
from .tools import ReservationAgent

try:
    from zoneinfo import ZoneInfo

    _MTL = ZoneInfo("America/Toronto")
except Exception:  # pragma: no cover
    _MTL = dt.timezone(dt.timedelta(hours=-4))

logger = logging.getLogger("yen-agent")


def _montreal_today() -> dt.date:
    return dt.datetime.now(_MTL).date()


def _build_stt(settings: Settings):
    # Deepgram Nova-3: monolingual English for the MVP, multilingual for FR/EN.
    if settings.is_multilingual:
        return deepgram.STT(model="nova-3", language="multi")
    return deepgram.STT(model="nova-3", language="en")


def _build_llm(settings: Settings):
    """Pick the runtime LLM.

    QUOTA WARNING: Google's free Gemini tier allows only ~20 requests **per day**
    per model — a single voice conversation exhausts it and every later turn dies
    with 429 RESOURCE_EXHAUSTED. Recommended alternatives:

      groq     free: 30 req/min, ~14,400/day, no card. Sub-100ms first token —
               the best latency for voice. OpenAI-compatible. (default)
      cerebras free: very high daily token volume.
      xai      xAI's Grok.
      openai   pay-as-you-go, no daily cap.
      livekit  routed through LiveKit Inference on your existing LiveKit key.
      google   fine for a couple of turns only (see above).
    """
    provider = (settings.llm_provider or "groq").lower()
    model = settings.llm_model

    if provider == "groq":
        # Groq exposes an OpenAI-compatible endpoint.
        return openai.LLM(
            model=model or "llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY"),
        )
    if provider == "cerebras":
        return openai.LLM.with_cerebras(model=model or "llama-3.3-70b")
    if provider in ("xai", "grok"):
        # xAI retired several models in 2026 — run `python scripts/check_setup.py`
        # to list what your account can actually use, then set YEN_LLM_MODEL.
        return openai.LLM.with_x_ai(model=model or "grok-4-1-fast-non-reasoning")
    if provider == "livekit":
        from livekit.agents import inference

        return inference.LLM(model=model or "google/gemini-2.5-flash-lite")
    if provider == "openai":
        return openai.LLM(model=model or "gpt-4o-mini")
    return google.LLM(model=model or "gemini-2.5-flash-lite")


def _build_tts(settings: Settings):
    """Deepgram Aura-2 — one vendor for both STT and TTS, on one API key.

    Deliberately single-provider: every extra vendor is another key that can
    expire and another bill that can fail on a system meant to run unattended.
    """
    return deepgram.TTS(model="aura-2-thalia-en")


def _build_turn_handling(settings: Settings) -> TurnHandlingOptions:
    """Semantic turn detection + preemptive generation (agents SDK >= 1.6.6 API).

    The hosted ``inference.TurnDetector`` runs on LiveKit Cloud (included on the
    free Build tier), so it is only enabled when LiveKit credentials are present
    — in plain ``console`` mode without a cloud project we fall back to VAD
    turn-taking rather than fail at runtime.
    """

    # Preemptive generation: start the LLM as soon as the caller is *likely*
    # done, discarding the draft if they keep talking — cuts perceived latency.
    opts = TurnHandlingOptions(preemptive_generation={"enabled": True})
    if os.environ.get("LIVEKIT_API_KEY") and os.environ.get("LIVEKIT_URL"):
        try:
            from livekit.agents import inference

            opts["turn_detection"] = inference.TurnDetector()
        except Exception:  # pragma: no cover - keep the call alive regardless
            logger.warning("Hosted turn detector unavailable; using VAD turn-taking.")
    else:
        logger.info("No LiveKit credentials; using VAD turn-taking (console mode).")
    return opts


async def entrypoint(ctx: JobContext) -> None:
    load_dotenv()
    settings = Settings.from_env()

    service = build_service(settings)
    locale = "fr" if settings.is_multilingual else "en"
    today = _montreal_today()
    concierge = Concierge(service, locale=locale, today=today)
    agent = ReservationAgent(
        concierge,
        instructions=system_instructions(
            multilingual=settings.is_multilingual, today=today.isoformat()
        ),
    )

    # VAD: AgentSession bundles silero by default, so no explicit vad= needed.
    session = AgentSession(
        stt=_build_stt(settings),
        llm=_build_llm(settings),
        tts=_build_tts(settings),
        turn_handling=_build_turn_handling(settings),
    )

    # -- observability: log per-turn metrics and a usage summary at end -----
    usage = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)
        usage.collect(ev.metrics)

    async def _log_usage() -> None:
        logger.info("call usage summary: %s", usage.get_summary())

    ctx.add_shutdown_callback(_log_usage)
    ctx.add_shutdown_callback(service.aclose)

    # Krisp telephony noise cancellation (BVC) is a LiveKit Cloud feature, so it
    # only applies when connected with credentials — not in local console mode.
    room_input_options = None
    has_cloud = bool(os.environ.get("LIVEKIT_API_KEY") and os.environ.get("LIVEKIT_URL"))
    if noise_cancellation is not None and has_cloud:
        try:
            room_input_options = RoomInputOptions(noise_cancellation=noise_cancellation.BVC())
        except Exception:  # pragma: no cover - keep the call alive regardless
            logger.info("noise cancellation unavailable; continuing without it.")

    await session.start(agent=agent, room=ctx.room, room_input_options=room_input_options)
    await ctx.connect()

    greeting = GREETING_FR if settings.is_multilingual else GREETING_EN
    # say_verbatim: the model otherwise pads the greeting into a ~13s monologue.
    await session.say(greeting, allow_interruptions=True)


def main() -> None:
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
