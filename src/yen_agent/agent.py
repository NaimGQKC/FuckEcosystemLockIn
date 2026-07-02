"""LiveKit Agents entrypoint and voice-stack wiring for the Yen agent.

Run modes (after `pip install -e ".[agent]"` and filling in `.env`):

    python -m yen_agent.agent console   # local terminal audio, no server
    python -m yen_agent.agent dev       # connect to LiveKit Cloud + browser test

The reservation backend is chosen by env (`YEN_RESERVATION_BACKEND`), defaulting
to the in-process mock — so this runs end-to-end with no Libro credentials.

Structure follows LiveKit's recommended patterns: a `prewarm` hook that loads
VAD once per worker process, metrics + usage collection, semantic turn
detection, telephony noise cancellation, and the current date injected into the
prompt so relative dates ("this Friday") resolve correctly.

Model identifiers below are the recommended low-cost stack. Plugin model names
occasionally change between releases; verify them against the installed plugin
version if a model isn't found.
"""

from __future__ import annotations

import datetime as dt
import logging

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
)
from livekit.plugins import deepgram, silero

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
    if settings.llm_provider == "openai":
        from livekit.plugins import openai

        return openai.LLM(model="gpt-4o-mini")
    from livekit.plugins import google

    return google.LLM(model="gemini-2.5-flash-lite")


def _build_tts(settings: Settings):
    if settings.tts_provider == "cartesia":
        from livekit.plugins import cartesia

        return cartesia.TTS(model="sonic-2", language="fr" if settings.is_multilingual else "en")
    return deepgram.TTS(model="aura-2-thalia-en")


def _build_turn_detection(settings: Settings):
    try:
        if settings.is_multilingual:
            from livekit.plugins.turn_detector.multilingual import MultilingualModel

            return MultilingualModel()
        from livekit.plugins.turn_detector.english import EnglishModel

        return EnglishModel()
    except Exception:  # pragma: no cover - optional model download
        logger.warning("Turn-detector model unavailable; falling back to VAD turn-taking.")
        return None


def prewarm(proc: JobProcess) -> None:
    """Load the (heavier) VAD model once per worker process, not per call."""
    proc.userdata["vad"] = silero.VAD.load()


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

    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()
    session_kwargs = dict(
        stt=_build_stt(settings),
        llm=_build_llm(settings),
        tts=_build_tts(settings),
        vad=vad,
        # Start generating a response as soon as the caller is likely done,
        # which cuts perceived latency; safe to keep on with turn detection.
        preemptive_generation=True,
    )
    turn_detection = _build_turn_detection(settings)
    if turn_detection is not None:
        session_kwargs["turn_detection"] = turn_detection

    session = AgentSession(**session_kwargs)

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

    # Krisp telephony noise cancellation improves narrowband phone audio.
    room_input_options = None
    try:
        from livekit.plugins import noise_cancellation

        room_input_options = RoomInputOptions(noise_cancellation=noise_cancellation.BVC())
    except Exception:  # pragma: no cover - optional plugin
        logger.info("noise_cancellation plugin not installed; continuing without it.")

    await session.start(agent=agent, room=ctx.room, room_input_options=room_input_options)
    await ctx.connect()

    greeting = GREETING_FR if settings.is_multilingual else GREETING_EN
    await session.generate_reply(instructions=f"Greet the caller with: {greeting}")


def main() -> None:
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))


if __name__ == "__main__":
    main()
