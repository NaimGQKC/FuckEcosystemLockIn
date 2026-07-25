# Why we chose each piece of the stack

Written to be defensible out loud. Every entry: what it is in plain terms, what we
compared it against, why we picked it, **what we gave up**, and when we'd choose
differently. If you can't state the downside of a choice, you don't understand it
well enough to defend it.

## The goal these choices serve

**Deploy to one restaurant and never have to touch it again**, at low cost.

That is a stricter requirement than "own your stack", and it changes the ranking.
Every choice below is now judged on three things, in order:

1. **Unattended reliability** — will this still work in eight months with nobody
   watching it? Anything that can silently expire is a defect, not a saving.
2. **Cost** — but note the costs here are dominated by *fixed* monthly items
   (phone number, hosting), not usage. At ~90 talk-minutes/month the AI itself is
   a couple of dollars.
3. **Speed** — every 100ms is audible to a caller.

Two consequences worth stating up front, because they reverse earlier decisions:

* **Free tiers are a liability, not a saving.** A free tier that lapses takes the
  restaurant's phone down. Production runs on paid plans with a card on file.
* **Fewer vendors beats better vendors.** Each extra provider is another key that
  can expire and another bill that can fail. We consolidated onto Deepgram for
  both STT and TTS and dropped Cartesia entirely.

---

## The big one: LiveKit Agents (voice orchestration)

**What it does.** Runs the real-time loop: capture caller audio → speech-to-text →
LLM → text-to-speech → play back, while handling the hard parts — interruptions
(barge-in), knowing when the caller finished speaking (turn detection), echo
cancellation, and bridging phone calls in over SIP.

**Alternatives considered**

| Option | What it is | Why not |
|---|---|---|
| **Vapi** | Managed voice-agent platform. What Sadie uses. | ~$0.05/min platform fee on top of model costs; your prompt and call data live in their system. Fastest to ship, least ownership — the opposite of this project's point. |
| **Retell / Bland** | Same category as Vapi | Same trade: speed now, lock-in later. |
| **Pipecat** (open source) | Python framework, similar shape to LiveKit | Genuinely comparable. Smaller ecosystem, and no first-party WebRTC/SIP infrastructure — you assemble telephony yourself. |
| **Build on raw WebSockets** | Wire up Deepgram + LLM + TTS yourself | We'd spend weeks reimplementing barge-in and turn detection badly. Not a real option. |

**Why LiveKit**
- **Apache-2.0 open source.** The framework is ours; we can self-host the whole media stack if the economics ever demand it. That is literally the repo's thesis.
- **Every layer is swappable by config** — STT, LLM, TTS are plugins. We've already switched LLM providers four times without touching agent code.
- Solves the genuinely hard real-time problems (semantic turn detection, barge-in, echo cancellation) that we would otherwise get wrong.
- Phone support comes free: a SIP caller is just another participant in a room, so **the same agent works on the browser and the phone with zero code changes.**
- Ships a first-party **eval/simulation framework** (`livekit.agents.evals`) for testing conversations.

**What we gave up**
- **More moving parts than a managed platform.** We debug plugin versions, deprecations, and Windows quirks ourselves — we've hit all three.
- We currently lean on **LiveKit Cloud** for hosted turn detection and noise cancellation. That's a soft dependency: it degrades gracefully (falls back to VAD) but the best behaviour is on their infrastructure.
- **API churn.** 1.6.4 → 1.6.6 deprecated things under us mid-project.

**Re-examined against "deploy once and never touch it."** That goal is Vapi's strongest argument, so it deserves a straight answer rather than a slogan. It still doesn't win, for one concrete reason: **Vapi replaces the voice loop, not the ops.** The Libro integration is custom either way, so with Vapi you still host a webhook server for the booking tools — same deployment, same thing to keep alive — plus a per-minute platform fee, plus the loss of being able to fix the pipeline yourself when Libro's private API shifts under us (which it will). You'd add a dependency and remove almost no work.

**When we'd genuinely choose differently:** if the restaurant needed *no* custom backend integration — just an FAQ bot and a calendar — Vapi would be the right call and this repo would be over-engineering.

---

## Speech-to-text: Deepgram Nova-3

**Alternatives:** OpenAI Whisper (self-host), AssemblyAI, Google, Azure, AWS.

**Why Deepgram**
- Built for **streaming** — partial results as the caller speaks, which is what makes sub-second response possible. Whisper is batch-first; it transcribes after you stop talking.
- **Trained on telephony audio.** Phone calls are 8 kHz narrowband — much worse than a podcast mic — and most models are trained on clean audio.
- **Real-time code-switching across 10 languages** including French — one setting turns on EN/FR auto-detection, which Montreal needs.
- $200 free credit, per-second billing, and it does **both STT and TTS on one key**.

**What we gave up / what worries me**
- **No published French-Canadian accuracy figure for Nova-3.** An independent Québécois benchmark (CRIM, 24 models) puts `whisper-large-v3-turbo` at 8.2% word error rate and shows that models topping the standard benchmarks can do *badly* on real Québécois. We're choosing partly on faith.
- Add restaurant noise and plan for **15–25% real-world error rate**, not 8%.
- **This is the one choice I'd test before committing** — 20–30 hand-transcribed real calls would settle it.

---

## Text-to-speech: Deepgram Aura-2 (both languages)

**Alternatives:** ElevenLabs, Cartesia, OpenAI, Azure, AWS Polly.

**Why:** Aura-2 is the cheapest good option (~$0.018/min) and shares the Deepgram key — measured **240ms to first audio** in our own logs, which is excellent. ElevenLabs sounds best but costs 3-6x.

**We dropped Cartesia.** It was in the stack only to give French a native voice. We never had a Cartesia key, it was never exercised in a real call, and a second TTS vendor is a second key that can expire on an unattended system. One vendor, one key, one bill. If French output turns out to sound wrong, revisit — but with evidence from a real call, not on spec.

**What we gave up — and this one is a real problem for Montreal.** None of the fast providers (Deepgram, ElevenLabs, Cartesia, OpenAI) has a genuine **Québécois** voice. Real fr-CA voices exist essentially only on **Azure** and **AWS Polly (Gabrielle)** — the slower stacks. So for French we may have to trade latency for sounding local. Whether a Parisian accent actually costs trust in Montreal is **untested** — worth making our own A/B once there's volume.

---

## LLM: Groq (Llama 3.3 70B), swappable

**Alternatives tried in this project:** Google Gemini, xAI Grok, OpenAI, Cerebras, LiveKit Inference.

**Why Groq**
- **Purpose-built inference hardware** (LPUs) → the fastest first-token latency available, which is the single biggest contributor to voice lag.
- OpenAI-compatible API, so switching costs nothing.
- Its free tier (~30 req/min) is generous enough for development. Gemini's is **20 requests per day** — one conversation exhausted it and killed our first live test.

**Production note: we do not ship on a free tier.** The free tier is a development convenience only. An unattended restaurant phone line cannot depend on a quota that can lapse or be revoked without notice — production runs on a paid plan with a card on file. At this volume that is a couple of dollars a month.

**What we gave up**
- Open-weight models are **weaker at tool calling** than GPT-4-class models. Our tools are simple, so it holds — but it's the reason to keep the swap easy.

**Open decision — the model itself.** `llama-3.3-70b-versatile` measured a **3.55s worst-case** first token, roughly 4x over the ~800ms budget. A smaller model would be faster *and* cheaper *and* less prone to timeouts — three of three on our stated criteria. This is a benchmark we should actually run rather than reason about: same 20 prompts through each candidate, measuring time-to-first-token and whether it picks the right tool. **Not done yet.**

**Key design point:** the LLM is the *most* replaceable part. It only converses and calls tools; it never does math, dates, or availability. That's deliberate — see below.

---

## The architectural decision that matters most: `ReservationService`

**What it is.** One Python interface (`check_availability`, `create_booking`,
`cancel_booking`, …). Everything above it — the agent, the tools, the conversation
logic — talks *only* to that interface. Two implementations exist: a local fake and
the real Libro API.

**Why it matters**
- We built and tested the entire agent for days **before** we had any Libro access.
- When the real API turned out to be **completely different** from the documented one (per-endpoint API versions, "services" that are actually 15-minute slots, a datetime derived from a relationship rather than a field), **only one file changed.** The agent, tools, prompts and 83 tests were untouched.
- It makes the system **testable without the network** — the whole suite runs in ~6 seconds with no API keys.
- It's the anti-lock-in mechanism: swapping Libro for OpenTable is one new file.

**What we gave up:** one extra layer of indirection, and domain models that must be translated at the boundary. Trivially worth it — this is the decision I'd defend hardest in an interview, because it's the one that actually paid off under pressure.

**Related and equally deliberate: the LLM never does math.** Dates ("this Friday"), phone-number formatting, and table-capacity logic are all deterministic Python. LLMs are unreliable at calendar arithmetic and there's no reason to gamble on it — same input, same output, every time, and unit-testable.

---

## Python

**Alternative:** Node/TypeScript (LiveKit supports both).

**Why:** the voice/AI ecosystem is Python-first — LiveKit's own examples, evals, and most plugins land there first. And it's the natural language for the deterministic logic layer.

**Gave up:** TypeScript's type safety would have caught a couple of our bugs at compile time rather than runtime.

---

## FastAPI + SQLite (the mock Libro service)

**Why FastAPI:** async (matches the agent), automatic validation, and it can serve the future operator webapp too — one framework instead of two.

**Why SQLite:** zero setup, a file, perfect for a fake service.

**Reversed decision — SQLite stays, for production too.** An earlier version of this
document recommended Postgres for the operator webapp. That was the right answer to
the wrong question. Postgres is a *service*: something to run, back up, patch, and
upgrade. For one restaurant with a handful of calls a day and a "never touch it
again" mandate, that is pure operational cost for capacity we will never use.
SQLite is a file that needs nothing from anyone. If this ever grows to many
restaurants with concurrent writers, revisit — that is the trigger, not taste.

**httpx** over `requests` because it's async and supports in-process ASGI transport — that's how our tests hit the mock API with no network at all.

---

## Telephony (Phase 2, not built yet): Twilio

**Alternatives:** Telnyx, Plivo, Vonage, LiveKit's own numbers.

**Why Twilio:** LiveKit's first-party numbers are **US-only**, and we need a Montreal 514/438 number. Twilio is the best-documented SIP path, ~$1.15/month plus ~$0.0045/min.

**Gave up:** Telnyx is slightly cheaper. Not worth optimizing at this volume.

---

## For the operator webapp (decision pending)

| Choice | Recommendation | Why |
|---|---|---|
| Backend | **FastAPI** | Already in the stack; same language as the agent; async |
| Database | **Postgres** | Concurrent writes, JSON columns for transcripts, real numeric types |
| Frontend | **Server-rendered HTML + a little JS**, not React | It's a call list, a transcript view, and a few counters for one restaurant. A React/Next.js build adds a toolchain, a deploy target, and hours of work for a page that renders a table. **Reach for React when there's real client-side state — there isn't.** |
| Charts | A small chart library, or plain HTML/CSS bars | Same reasoning |

The honest interview answer here is *"we chose the boring option deliberately, because the complexity budget belongs in the voice pipeline, not in the admin page."*

---

## What is actually proven, and what is not

Be precise about this — it is easy to over-claim, and the mock makes it easy to
fool yourself.

| Claim | Status |
|---|---|
| Booking against **real Libro**, real restaurant | ✅ **Proven.** Booking `111634069` created on `api.libroreserve.com` (restaurant 8169), requested 11:30 EDT returned as `2026-09-08T15:30:00Z` — exact — then cancelled and independently verified. |
| Conversation logic, dates, phone parsing, the cascade | ✅ Proven by 93 tests. |
| **Table merging / combining tables** | ❌ **NOT proven, and not real.** That runs on `mock_libro/floorplan.py`, an *invented* floor plan. Real Libro does its own seating; the live adapter never calls it. Do not cite the demo as evidence about YEN's dining room. |
| **Voice → real Libro, end to end** | ❌ **Never run.** Text-mode logic against real Libro: yes. Someone actually *speaking* to the agent while it books a real table: never. This is the biggest untested gap. |
| French-Canadian speech accuracy | ❌ Unvalidated. Chosen on reputation. |
| Latency under real phone conditions | ❌ Unmeasured end to end. |

---

## Where this stack is weakest (say this before they find it)

1. **We're on a reverse-engineered private API.** Libro's official partner route never responded, so we integrate against the dashboard's own undocumented API. It can change without notice. Mitigated by isolating it behind one adapter, but it's the biggest business risk.
2. **French-Canadian speech accuracy is unvalidated.** We chose the STT on reputation, not local evidence.
3. **No conversation-level tests yet.** 83 tests prove the *logic*; nothing yet proves the *conversation*. The SDK ships the tooling; we haven't used it.
4. **Soft dependency on LiveKit Cloud** for the best turn detection.
5. **Cost honesty:** at this venue's real volume (~91 talk-minutes/month), infrastructure is ~$10/month, but fully loaded with maintenance it's roughly at parity with buying a SaaS product. **The justification is control and data ownership, not savings** — claiming otherwise is easy to pick apart.
