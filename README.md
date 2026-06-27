# Yen — bilingual voice AI phone agent (POC)

A low-cost, fast-to-ship voice agent that answers Yen Restaurant's (Montreal)
phone and handles reservations — check availability, book, look up, reschedule,
cancel, answer FAQs, and take messages — in **English first, French via one
config switch**.

This repository is **Phase 1**: a $0, web-testable agent built on
[LiveKit Agents](https://docs.livekit.io/agents/), wired to a **mock Libro
reservation API** so the whole thing runs end-to-end with no Libro credentials
and no phone number. Going live later is mostly configuration, not a rewrite.

## The one idea that makes this cheap and safe

Every reservation tool depends only on the `ReservationService` abstraction
(`src/yen_agent/reservation/base.py`). Two interchangeable implementations:

| Implementation | Backend | When |
|---|---|---|
| `MockReservationService` | local FastAPI + SQLite (`mock_libro/`) | Phase 1 POC, tests |
| `LibroReservationService` | real Libro JSON:API + OAuth | Phase 3, after partner access |

They share one JSON:API client (`reservation/jsonapi.py`); only base URL + auth
differ. **Swapping mock → real Libro is a one-line change** (`YEN_RESERVATION_BACKEND=libro`).
The agent and its tools never import HTTP or Libro specifics.

```
caller ─▶ LiveKit AgentSession (STT → LLM → TTS)
              │
              ▼
        ReservationAgent  (tools.py, @function_tool)
              │  delegates to
              ▼
          Concierge   (concierge.py — spoken responses, error handling)
              │  depends only on
              ▼
       ReservationService  (ABC)
          ├── MockReservationService ─▶ mock_libro (FastAPI + SQLite)
          └── LibroReservationService ─▶ api.staging.libro.app
```

## Quick start

### 1. Run the test suite ($0, no keys, ~0.2s)

The reservation layer, the Libro-shaped mock, and the concierge logic are fully
covered without any cloud services or the heavy agent runtime:

```bash
pip install -e ".[dev]"
pytest -q          # 24 tests: mock JSON:API shapes, service round-trips, concierge speech
```

### 2. Run the mock Libro server (optional — tests use it in-process)

```bash
python -m mock_libro --port 8000       # serves the Libro-shaped JSON:API
curl "http://localhost:8000/restricted/restaurant/seatings?date=2026-07-20&size=2"
```

### 3. Run the voice agent

```bash
pip install -e ".[agent]"              # installs livekit-agents + plugins
cp .env.example .env                   # fill in LiveKit + Deepgram + LLM keys
python agent.py console                # local terminal audio, no server needed
# or:
python agent.py dev                    # connect to LiveKit Cloud, test in the browser Agent Console
```

The agent defaults to the in-process mock reservation backend, so it works the
moment your STT/LLM/TTS keys are set — no Libro access required.

## Recommended low-cost stack

English-first MVP, each layer swappable via `.env`:

| Layer | Choice | Notes |
|---|---|---|
| Framework | LiveKit Agents (Apache-2.0) | self-host worker = $0 |
| STT | Deepgram Nova-3 (`en`) | `multi` enables FR/EN code-switching |
| LLM | Gemini 2.5 Flash-Lite (or GPT-4o-mini) | cheap; tool-calling is simple here |
| TTS | Deepgram Aura-2 (`en`) | switch to Cartesia Sonic for French |
| Telephony (Phase 2) | Twilio Canadian local number → LiveKit SIP | LiveKit phone numbers are US-only |

### Enabling French

```dotenv
YEN_LANGUAGE_MODE=multi      # Nova-3 Multilingual STT + French greeting/locale
YEN_TTS_PROVIDER=cartesia    # Sonic for native French TTS
```

No architecture change — the agent detects the caller's language and responds in kind.

## Phased plan

- **Phase 1 (this repo):** free, web-tested agent against the mock. ✅
- **Phase 2:** buy a Twilio CA number, bridge via LiveKit SIP, test a real call.
- **Phase 3:** set `YEN_RESERVATION_BACKEND=libro` with partner credentials, run
  the same eval suite against Libro staging, certify, go live.

Request Libro partner access in parallel (email `admin@libroreserve.com`) — it
gates production and is outside our timeline, which is exactly why we build
against a mock first.

## Cost: an honest note

The detailed pricing in the project brief is a useful **2026 estimate**, but LLM
/ STT / TTS list prices change frequently — **re-verify before committing.**
Rough shape:

- **Phase 1 (this repo): $0.** No phone number, free LiveKit Build tier + provider
  free credits, worker on your laptop.
- **First live month:** largely absorbed by free credits — likely **single/low
  double digits out of pocket** (mostly the ~$1/mo Twilio number).
- **Sustained phone traffic (~1,500–2,000 min/mo):** realistically **~$80–$130/mo**
  once free credits are exhausted — **higher than the ~$60 one-time figure** in the
  brief. The $60 comfortably covers the POC plus the first live month; ongoing
  service needs a recurring budget. **Flag this to the owner up front.**

TTS is the largest and most variable cost (it scales with how much the agent
*speaks*), so the agent is written to keep responses short.

## Project layout

```
mock_libro/            # the "external" Libro service: FastAPI + SQLite JSON:API mock
  app.py               #   endpoints + JSON:API serializers + error codes
  db.py                #   SQLite store, Yen seed data, seating/availability rules
src/yen_agent/
  reservation/         # the swap point
    base.py            #   ReservationService ABC  ← tools depend only on this
    models.py          #   provider-agnostic domain models
    errors.py          #   Libro error-code → typed exception mapping
    jsonapi.py         #   shared httpx JSON:API client
    mock.py            #   MockReservationService (in-process or http)
    libro.py           #   LibroReservationService (real, OAuth) — Phase 3
  concierge.py         # reservation orchestration + spoken responses (no LiveKit)
  tools.py             # LiveKit @function_tool wrappers
  agent.py             # AgentSession wiring + entrypoint
  prompts.py / faq.py  # system prompt + Yen FAQ knowledge base
  config.py            # env-driven settings
tests/                 # 24 tests, run with no cloud services
docs/LIBRO_CONTRACT.md # the JSON:API subset the mock mirrors + caveats
```

## Disclosure

The agent tells callers it's an AI assistant and always offers a path to a human
or to leave a message — good practice, and required in some jurisdictions.

> The FAQ facts (hours, address, menu) in `src/yen_agent/faq.py` are **placeholders
> for the demo** — replace with Yen's real details before any live use.
