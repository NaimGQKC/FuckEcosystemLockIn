# Why we chose each piece of the stack

Written to be defensible out loud. Every entry: what it is in plain terms, what we
compared it against, why we picked it, **what we gave up**, and when we'd choose
differently. If you can't state the downside of a choice, you don't understand it
well enough to defend it.

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

**When we'd choose differently.** If the goal were "ship one restaurant this week and never touch it," Vapi is the correct answer and I'd say so. We chose LiveKit because the brief is ownership.

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

## Text-to-speech: Deepgram Aura-2 (English) / Cartesia Sonic (French)

**Alternatives:** ElevenLabs, OpenAI, Azure, AWS Polly.

**Why:** Aura-2 is the cheapest good option (~$0.018/min) and shares the Deepgram key — measured **240ms to first audio** in our own logs, which is excellent. Cartesia covers French with sub-100ms latency. ElevenLabs sounds best but costs 3–6×.

**What we gave up — and this one is a real problem for Montreal.** None of the fast providers (Deepgram, ElevenLabs, Cartesia, OpenAI) has a genuine **Québécois** voice. Real fr-CA voices exist essentially only on **Azure** and **AWS Polly (Gabrielle)** — the slower stacks. So for French we may have to trade latency for sounding local. Whether a Parisian accent actually costs trust in Montreal is **untested** — worth making our own A/B once there's volume.

---

## LLM: Groq (Llama 3.3 70B), swappable

**Alternatives tried in this project:** Google Gemini, xAI Grok, OpenAI, Cerebras, LiveKit Inference.

**Why Groq**
- **Free tier that survives real use**: ~30 requests/min, ~14,400/day. Gemini's free tier is **20 requests per day** — one conversation exhausted it and killed our first live test.
- **Purpose-built inference hardware** (LPUs) → the fastest first-token latency available, which is the single biggest contributor to voice lag.
- OpenAI-compatible API, so switching costs nothing.

**What we gave up**
- Open-weight models are **weaker at tool calling** than GPT-4-class models. Our tools are simple, so it holds — but it's the reason to keep the swap easy.
- We measured a **3.55s worst-case** first token on the 70B model — over budget. The mitigation is `llama-3.1-8b-instant`, untested so far.

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

**Why SQLite:** zero setup, a file, perfect for a fake service. **For the real webapp we should move to Postgres** — concurrent writes, proper types (their call records store duration as a *string*, which breaks aggregation), and JSON columns for storing raw call transcripts.

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

## Where this stack is weakest (say this before they find it)

1. **We're on a reverse-engineered private API.** Libro's official partner route never responded, so we integrate against the dashboard's own undocumented API. It can change without notice. Mitigated by isolating it behind one adapter, but it's the biggest business risk.
2. **French-Canadian speech accuracy is unvalidated.** We chose the STT on reputation, not local evidence.
3. **No conversation-level tests yet.** 83 tests prove the *logic*; nothing yet proves the *conversation*. The SDK ships the tooling; we haven't used it.
4. **Soft dependency on LiveKit Cloud** for the best turn detection.
5. **Cost honesty:** at this venue's real volume (~91 talk-minutes/month), infrastructure is ~$10/month, but fully loaded with maintenance it's roughly at parity with buying a SaaS product. **The justification is control and data ownership, not savings** — claiming otherwise is easy to pick apart.
