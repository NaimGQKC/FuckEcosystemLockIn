# YEN Cuisine Japonaise — bilingual voice AI phone agent (POC)

A low-cost, fast-to-ship voice agent that answers the phone for **YEN Cuisine
Japonaise** (2157 Rue Mackay, downtown Montreal) and handles reservations —
check availability, book, look up, reschedule, cancel, answer FAQs, and take
messages — in **English first, French via one config switch**.

It doesn't just read a calendar: it reasons about the actual **floor plan** —
picking the right table, **combining tables** for larger parties, respecting how
long a table is held, and **escalating oversized parties to staff** — by calling
a deterministic seating engine rather than guessing.

> **For the developer:** hand the owner
> [`docs/OWNER_QUESTIONNAIRE.md`](docs/OWNER_QUESTIONNAIRE.md) — it collects the
> real hours, tables, and policies (with sensible defaults) needed to make the
> agent exact. Everything runs on realistic placeholders until then.

This repository is **Phase 1**: a $0, web-testable agent built on
[LiveKit Agents](https://docs.livekit.io/agents/), wired to a **mock Libro
reservation API** so the whole thing runs end-to-end with no Libro credentials
and no phone number. Going live later is mostly configuration, not a rewrite.

## The one idea that makes this cheap and safe

Every reservation tool depends only on the `ReservationService` abstraction
(`src/yen_agent/reservation/base.py`). Two interchangeable implementations:

| Implementation | Backend | When |
|---|---|---|
| `MockReservationService` | local FastAPI + SQLite (`mock_libro/`) | POC, demos, tests |
| `LibroPrivateReservationService` | **real YEN reservations** via the Libro dashboard API (token auth) | production ([guide](docs/LIBRO_PRIVATE_INTEGRATION.md)) |
| `LibroReservationService` | Libro partner OAuth API | unused (partner route didn't respond) |

**Swapping mock → real is a config change** (`YEN_RESERVATION_BACKEND=libro-private`).
The agent and its tools never import HTTP or Libro specifics — each backend keeps
its own wire-format details in one file.

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
          ├── MockReservationService        ─▶ mock_libro (FastAPI + SQLite)
          └── LibroPrivateReservationService ─▶ api.libroreserve.com (YEN, id 8169)
```

## Quick start

### 1. Run the test suite ($0, no keys, ~0.2s)

The reservation layer, the Libro-shaped mock, and the concierge logic are fully
covered without any cloud services or the heavy agent runtime:

```bash
pip install -e ".[dev]"
pytest -q          # 59 tests: floor plan, mock JSON:API, service round-trips, dates, phones, concierge
```

### 2. Run the mock Libro server (optional — tests use it in-process)

```bash
python -m mock_libro --port 8000       # serves the Libro-shaped JSON:API
curl "http://localhost:8000/restricted/restaurant/seatings?date=2026-07-20&size=2"
```

### 3. See the reasoning without any keys (text demo)

```bash
python scripts/demo.py
```

This drives the agent's brain through a real script — books a 2-top, combines
tables for a party of 8, refuses a second party of 8 when the room is full, and
escalates a party of 14 to staff — printing exactly what it would say.

### 4. Run the actual voice agent

See **[Run it for real](#run-it-for-real-with-your-own-keys)** below for the
full key-by-key setup. The short version:

```bash
pip install -e ".[agent]"              # installs livekit-agents + plugins
cp .env.example .env                   # fill in LiveKit + Deepgram + LLM keys
python agent.py console                # talk to it in your terminal, no server/phone needed
```

The agent defaults to the in-process mock reservation backend, so it works the
moment your STT/LLM/TTS keys are set — no Libro access required.

## Run it for real (with your own keys)

To actually **hear and talk to it**, you need three free accounts. None require
a phone number for the first test; all have free tiers.

| # | Account | Free tier | What you copy into `.env` |
|---|---|---|---|
| 1 | [LiveKit Cloud](https://cloud.livekit.io) | Build tier, no card | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| 2 | [Deepgram](https://console.deepgram.com) | $200 credit, no card | `DEEPGRAM_API_KEY` (used for both STT and TTS) |
| 3 | [Google AI Studio](https://aistudio.google.com/apikey) (Gemini) | free tier | `GOOGLE_API_KEY` |

(Prefer OpenAI for the LLM? set `YEN_LLM_PROVIDER=openai` and `OPENAI_API_KEY` instead.)

**Step by step:**

1. `pip install -e ".[agent]"` — installs `livekit-agents` and the Deepgram /
   Google plugins.
2. `cp .env.example .env`, then paste in the three keys above. The file has a
   clearly marked **REQUIRED** block at the top — 5 values, each annotated with
   the exact page to copy it from.
3. **Check your setup before starting:**
   ```bash
   python scripts/check_setup.py
   ```
   This validates the `.env`, the installed packages, and makes live test calls
   to Deepgram / Google / LiveKit to confirm each key actually works — with a
   fix hint for anything wrong. Green means go.
4. **Talk to it locally — no phone, no server:**
   ```bash
   python agent.py console
   ```
   Speak into your mic; you'll hear the agent answer. Try: *"Do you have a table
   for two on Saturday evening?"* → *"Make it a party of eight"* → *"Actually
   we're fourteen."*
5. **Test in the browser** (shows the agent as it would behave deployed):
   ```bash
   python agent.py dev
   ```
   Then open your project's **Agent Console** in the LiveKit Cloud dashboard and
   click connect. This uses free WebRTC minutes, not telephony.
6. **Add a real phone number (Phase 2, optional):** buy a Twilio Canadian local
   number, create an Elastic SIP trunk, and point an inbound LiveKit SIP trunk +
   dispatch rule at the agent. No agent code changes — a phone caller is just
   another participant. (Costs ~$1/mo for the number + per-minute usage.)

**Enable French** any time: set `YEN_LANGUAGE_MODE=multi` and
`YEN_TTS_PROVIDER=cartesia` (+ `CARTESIA_API_KEY`).

> **Model-name note:** the plugin model ids in `src/yen_agent/agent.py`
> (Nova-3, `gemini-2.5-flash-lite`, `aura-2-thalia-en`, `sonic-2`) are the
> recommended stack; if a plugin version rejects one, check the provider's
> current model list and adjust that one line.

## Recommended low-cost stack

English-first MVP, each layer swappable via `.env`:

| Layer | Choice | Notes |
|---|---|---|
| Framework | LiveKit Agents (Apache-2.0) | self-host worker = $0 |
| STT | Deepgram Nova-3 (`en`) | `multi` enables FR/EN code-switching |
| LLM | Gemini 2.5 Flash-Lite (or GPT-4o-mini) | cheap; tool-calling is simple here |
| TTS | Deepgram Aura-2 (`en`) | switch to Cartesia Sonic for French |
| Telephony (Phase 2) | Twilio Canadian local number → LiveKit SIP | LiveKit phone numbers are US-only |

### Enabling French (auto-detected, including Québec French)

```dotenv
YEN_LANGUAGE_MODE=multi      # Nova-3 Multilingual STT + French greeting/locale
YEN_TTS_PROVIDER=cartesia    # Sonic for native French TTS (+ CARTESIA_API_KEY)
```

No architecture change — the agent detects the caller's language from their first
words and responds in kind, and can switch mid-call.

**What auto-detection actually covers.** Deepgram Nova-3's real-time
code-switching supports exactly **10 languages**: English, Spanish, French,
German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch. So:

| Language | Auto-detect + switch? |
|---|---|
| English | ✅ |
| French (incl. Québécois) | ✅ — Québec accent/idiom may cost some accuracy vs. Metropolitan French; worth testing with real callers |
| Spanish, German, Italian, Portuguese, … | ✅ (in the 10) |
| **Chinese (Mandarin/Cantonese)** | ❌ **not** in the code-switching set |

Chinese would need a different approach — either pinning STT to Chinese for a
dedicated line (losing auto-detect), or a different STT provider. Don't promise
trilingual EN/FR/ZH auto-switching on this stack without testing that path first.

## How the agent reasons about tables

The hard part of restaurant reservations isn't the calendar — it's the **room**.
All of that lives in `mock_libro/floorplan.py` as a deterministic engine (an LLM
should never do table math), and the agent reasons by *calling* it:

- **Floor plan:** YEN is modeled as an intimate room — a few 2-tops and 4-tops,
  one 6-top, and a sushi counter (placeholder inventory; confirm with the
  restaurant). Tables belong to **combinable groups** that can be pushed together.
- **Least-waste assignment:** for each request the engine picks the smallest
  single table that fits; if none fits, it **merges** the smallest set of tables
  in one group. A party of 8 becomes two combined 4-tops; the agent says so.
- **Turn time:** a booking holds its table(s) for the full sitting (lunch 75 min,
  dinner 105 min), so a 7 PM booking blocks *overlapping* times — not just the
  exact slot. A time can be open for two and full for eight.
- **Large-party escalation:** parties beyond what any arrangement can seat
  (currently 8) return a "needs staff" result; the agent stops trying to book and
  takes a message instead.
- **Hours & closed days:** lunch is offered Mon–Sat, dinner daily, each only up to
  a last-seating time — encoded as services, so the agent never offers a slot when
  the kitchen is closed.

`python scripts/demo.py` walks through all of these out loud. The same logic is
covered by `tests/test_floorplan.py` and `tests/test_reservation_service.py`.

## Robustness for real calls

The things that break voice agents in practice are handled deterministically
(not left to the model), following patterns from LiveKit's reference agents:

- **Dates** — callers say "this Friday", "tomorrow", "July 5". `datetime_resolve`
  turns those into real dates relative to today (in Montreal time), rolls
  past dates forward, and refuses dates in the past or beyond the booking
  horizon. Today's date is also injected into the prompt.
- **Phone numbers** — "(514) 555-1234", "514.555.1234", or spelled-out digits all
  normalize to one E.164 form, so a number given at booking matches at
  lookup/cancel. Invalid numbers are re-prompted, not silently accepted.
- **Remembered call state** — name, phone, and party size collected once persist
  for the rest of the call (LiveKit's `UserData` pattern), so the agent can
  cancel "the reservation under my number" without asking again.
- **Runtime** — bundled VAD, semantic turn detection + preemptive generation to
  cut latency, Krisp telephony noise cancellation (on LiveKit Cloud), and
  per-turn metrics + a usage summary per call.

## Phased plan

- **Phase 1 (this repo):** free, web-tested agent against the mock. ✅
- **Phase 2:** buy a Twilio CA number, bridge via LiveKit SIP, test a real call.
- **Phase 3 — real reservations:** set `YEN_RESERVATION_BACKEND=libro-private`
  with the YEN Libro token. First run the **read-only probe** to confirm the live
  API shapes, then a single controlled test booking. Full walkthrough:
  [`docs/LIBRO_PRIVATE_INTEGRATION.md`](docs/LIBRO_PRIVATE_INTEGRATION.md).

  ```bash
  python scripts/probe_libro_private.py --date 2026-08-15 --party 2   # safe, read-only
  ```

  The official Libro **partner** API (`LibroReservationService`) is stubbed but
  unused — that route didn't respond — so production goes through the dashboard
  API adapter instead.

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
  db.py                #   SQLite store, Yen seed data, table occupancy queries
  floorplan.py         #   tables, combinable groups, turn times, hours, assignment engine
src/yen_agent/
  reservation/         # the swap point
    base.py            #   ReservationService ABC  ← tools depend only on this
    models.py          #   provider-agnostic domain models
    errors.py          #   Libro error-code → typed exception mapping
    jsonapi.py         #   shared httpx JSON:API client
    mock.py            #   MockReservationService (in-process or http)
    libro_private.py   #   LibroPrivateReservationService — REAL YEN (token auth)
    libro.py           #   LibroReservationService (partner OAuth) — unused
  concierge.py         # reservation orchestration + spoken responses (no LiveKit)
  datetime_resolve.py  # deterministic natural-language date parsing
  phone.py             # phone-number normalization to E.164
  tools.py             # LiveKit @function_tool wrappers
  agent.py             # AgentSession wiring + entrypoint (prewarm, metrics)
  prompts.py / faq.py  # system prompt + Yen FAQ knowledge base
  config.py            # env-driven settings
scripts/demo.py        # text-mode walkthrough of the reservation reasoning
tests/                 # 59 tests, run with no cloud services
docs/OWNER_QUESTIONNAIRE.md  # questions for the restaurant owner (hand this off)
docs/LIBRO_CONTRACT.md       # the JSON:API subset the mock mirrors + caveats
```

## Disclosure

The agent tells callers it's an AI assistant and always offers a path to a human
or to leave a message — good practice, and required in some jurisdictions.

> The hours/address/menu in `src/yen_agent/faq.py` are drawn from public listings
> (the restaurant's site, OpenTable, Yelp, Tourisme Montréal). Third-party sources
> disagree slightly on exact hours, and the **table inventory in `floorplan.py` is
> a realistic placeholder** — confirm both with the restaurant before live use.
