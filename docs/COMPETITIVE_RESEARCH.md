# How production restaurant voice agents actually work — and what we should steal

Research: 24 Jul 2026. Sources are public marketing/engineering material plus the
LiveKit SDK installed in this repo (the SDK findings are verified locally; vendor
claims are their own marketing unless noted).

---

## 1. The single most important finding: Sadie AI is our exact competitor

**Sadie (heysadie.ai) is not a generic competitor — it is the incumbent for YEN's
precise situation**, and we should plan with that in mind rather than around it:

| | Sadie | Us |
|---|---|---|
| Origin | **Montreal** | Montreal |
| Reservation system | **Official Libro partner** (+ Now Book It, OpenTable) | Libro (reverse-engineered private API) |
| Languages | **Bilingual EN/FR by design** ("regulatory and market requirement for Quebec") | EN now, FR one config flag away |
| Pricing | $99 Answers (FAQ) / $199 Orders / $299 **Reserves** | our infra cost, ~$0.05/min |
| Concurrency | 20 concurrent calls | untested |
| Setup | < 24 hours | — |
| On every tier | transcripts, **sentiment-aware replies, call transfer** | transcripts no, transfer no |
| Claimed result | 700 calls/mo → 100+ bookings (one venue) | — |

**Strategic read.** Sadie has an *official* Libro partnership; we're on an
undocumented private API that can change without notice. We will not out-integrate
them. Our honest differentiation is the repo's thesis: **no vendor lock-in** — the
restaurant owns the logic, the data, and the prompt; can run bilingual, swap any
provider, and pay ~$0.05/min instead of $299/month. For a single venue Sadie is
probably the *rational* buy; our value is control, cost at scale, and the fact that
it's ours to extend. Worth saying plainly to the owner rather than pretending we
found a gap nobody noticed.

**What Sadie has that we don't (ranked by how much it matters):**
1. **Live call transfer to a human** — on *every* tier. We only take messages.
2. **Call transcripts + sentiment** surfaced to the operator.
3. Proven concurrency (20 simultaneous calls).
4. Takeout ordering with POS injection (out of scope for us).

---

## 2. Latency: the numbers the industry converged on

Consistent across Hamming AI, Telnyx, and several 2026 engineering write-ups:

| Round-trip (caller stops → agent starts) | Perceived |
|---|---|
| 300–800 ms | natural; the target |
| > 800 ms | noticeable awkward pauses |
| > 1500 ms | conversation feels broken |

- **Barge-in must complete in < 150 ms total** (detect → stop audio → cancel LLM →
  yield floor), with 30–50 ms per component.
- **Measure per-layer, not total.** The largest single contributor is almost always
  the LLM hop, then the SIP/CPaaS handoff.
- VAD needs ~95%+ accuracy or it false-triggers on background noise; most systems
  require 150–200 ms minimum speech duration before treating it as a barge-in.

**Where we actually are** (from our first working console run, measured):

| Stage | Ours | Verdict |
|---|---|---|
| TTS first byte (Aura-2) | **0.24 s** | good |
| LLM TTFT (llama-3.3-70b) | **0.69 s typical, 3.55 s worst** | worst case is 4× over budget |
| STT | Deepgram Nova-3 streaming | fine |
| EOU (turn detection) | 0.5–2.78 s observed | the 2.78 s is bad |

**Action:** llama-3.3-70b-versatile is too slow at the tail. Test
`YEN_LLM_MODEL=llama-3.1-8b-instant` — our tool schema is simple enough that an 8B
model should hold up, and Groq serves it far faster. A/B it before the demo.

---

## 3. Accuracy and the failure modes that actually bite

From Deepgram's own restaurant-ASR research and multiple production reports:

- **93–95% accuracy** on simple/moderate interactions is the realistic production
  ceiling — degrading with heavy accents, noise, and complex modifications.
- **Accented English carries a 5–15% miss rate**, worse on noisy lines. Directly
  relevant: Montreal callers, Québécois French, and multilingual guests.
- **The killer failure is dropped negation.** ASR drops the "no" in "no pickles" and
  the model receives a confident, *inverted* intent. For a restaurant this is the
  allergy case: **"no shellfish" → "shellfish"** is a safety incident, not a typo.
- **Confidence-based routing:** set a threshold (~70% is the common starting point)
  and hand off below it, with a trained opener: *"I'm not sure about that — let me
  get someone who can help."*
- **Never guess** allergens, prices, or hours. Load them as structured data.

**For us:** our FAQ is already structured and the prompt forbids inventing facts —
good. But we have **no readback of dietary notes** and **no confidence-based
escalation**. Both are real gaps.

---

## 4. Architecture patterns in production systems

- **Multi-agent with a triage/greeter** that classifies intent, then hands to a
  specialist (reservations / takeout / checkout / inquiries). This is LiveKit's own
  restaurant example and the pattern most vendors describe.
- **Shared state object across handoffs** (LiveKit's `UserData`), passing a truncated
  slice of chat history forward — not the whole transcript.
- **Confirmation before any destructive action** — universally recommended, and the
  one guardrail every source repeats.
- **Structured slots**: `party_size`, `date`, `time`, `name`, `phone`, `seating`.

**For us:** we're single-agent, which is *fine and arguably better* at our scope —
multi-agent adds handoff latency and failure modes for a system that only does
reservations. We already have shared state (`CallState`) and structured slots. The
gap is **enforced confirmation before booking**.

---

## 5. Testing: LiveKit ships an eval framework we're not using

**Verified locally** in `livekit-agents` 1.6.x — these modules exist in the SDK we
already depend on:

```python
from livekit.agents import evals, simulation

evals: Judge, JudgeGroup, EvaluationResult, JudgmentResult, Verdict,
       accuracy_judge, coherence_judge, conciseness_judge, handoff_judge,
       relevancy_judge, safety_judge, task_completion_judge, tool_use_judge
simulation: Scenario, ScenarioGroup, SimulationRun, SimulationVerdict,
            SimulationContext, ScenarioUserdata
```

Directly relevant judges: **`tool_use_judge`** ("tool selection, parameter accuracy,
output interpretation, error handling"), **`task_completion_judge`**, and
**`conciseness_judge`** ("critical for voice AI where brevity matters" — exactly the
13-second-greeting problem we just fixed).

Industry practice on top of that:
- **Golden-set regression**: 100–500 recorded calls that must pass every deploy.
- Test explicitly for: **interruptions, background noise, unavailable data, slow tool
  responses**.
- **Turn-level LLM judging** for relevance/safety/tone, feeding dashboards.
- Telephony edge cases: **DTMF keypad, answering-machine detection, voicemail,
  transfers, bad headset audio**.

**For us:** we have 83 unit tests of the *logic*, but **zero conversation-level
evals**. Our logic can be perfect while the agent still behaves badly. This is the
biggest testing gap and the SDK already provides the tools.

---

## 6. Production guardrails we're missing

From the LiveKit production checklist and vendor practice:

- Session recording **with PII redaction**
- **Out-of-domain detection** (caller asks something unrelated)
- **Response-length caps** (we do this by prompt only — not enforced)
- **Rate limits per caller**
- Confidence thresholds → human handoff

---

## 7. Prioritized backlog for our agent

**P0 — before any real customer takes a call**
1. **Enforced confirmation before booking.** Read back date, time, party size, name,
   and phone, and require an explicit yes. Today we only *ask* the model to confirm;
   nothing enforces it. Highest-risk gap.
2. **Read back dietary/allergy notes verbatim** and confirm — the dropped-negation
   failure is a safety issue.
3. **Latency fix**: A/B `llama-3.1-8b-instant`; target < 800 ms end-to-end.

**P1 — needed to be credible against Sadie**
4. **Live transfer to a human** during opening hours (Sadie has it on every tier).
5. **Conversation evals** using `livekit.agents.evals` + `simulation` — a golden set
   of scripted calls (book / merge table / full slot / large party / cancel /
   wrong number / silence / interruption) run on every change.
6. **Transcript capture** per call, with PII redaction, delivered to the owner.
7. **SMS/email confirmation** to the guest after booking.

**P2 — hardening**
8. Confidence-threshold escalation from STT.
9. Out-of-domain guard + per-caller rate limit.
10. Concurrency test (Sadie advertises 20; we've never run 2).
11. Québécois French accuracy test with a real speaker — Deepgram's French skews
    Metropolitan.

---

## 8. What to have Claude Cowork extract from Sadie

When you analyze Sadie directly, the high-value unknowns are **behavioural**, not
marketing. Try to capture:

1. **The greeting** — exact wording, length in seconds, and whether it discloses AI.
2. **Turn latency** — time from you finishing a sentence to it starting to speak.
3. **Confirmation flow** — does it read back the full reservation and require a yes?
   Does it spell names back? How does it capture a phone number (digit by digit?).
4. **Failure handling** — say something ambiguous, interrupt it mid-sentence, give a
   date that's closed, ask for a party of 15, ask about an allergy. Record verbatim
   what it says.
5. **Escalation** — how does it offer a human? Does it transfer live or take a message?
6. **Bilingual switching** — start in English, switch to French mid-call. Does it
   follow? Try Québécois idiom ("j'aimerais réserver pour à soir").
7. **Out-of-domain** — ask something irrelevant and see how it deflects.
8. **What it refuses to do**, and how gracefully.

Those transcripts are worth more than any feature list: they're the behavioural
spec we can test our agent against with `simulation.Scenario`.

---

## Sources

Vendor/marketing: [Sadie](https://www.heysadie.ai/),
[Sadie×Libro partnership](https://librorez.com/news/libro-sadie-ai-partnership-restaurant-reservation/),
[Sadie on OpenTable](https://support.opentable.com/s/article/sadieai?language=en_US),
[Now Book It intro](https://www.nowbookit.com/tools-and-tips/introducing-sadie-ai-phone-agent/),
[Slang.ai](https://www.slang.ai/), [Loman](https://loman.ai/).

Engineering: [Hamming — voice AI latency](https://hamming.ai/resources/voice-ai-latency-whats-fast-whats-slow-how-to-fix-it),
[Hamming — testing LiveKit agents](https://hamming.ai/blog/how-to-test-voice-agents-built-with-livekit),
[Telnyx latency benchmark](https://telnyx.com/resources/voice-ai-agents-compared-latency),
[Agora — 10 lessons](https://prod.agora.io/en/blog/lessons-learned-building-voice-ai-agents),
[Deepgram — restaurant ASR accents](https://deepgram.com/learn/restaurant-voice-ai-asr-accent-variability-multi-region-ordering),
[Future AGI — barge-in guide](https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026/),
[LiveKit testing docs](https://docs.livekit.io/agents/start/testing/),
[Towards AI — 7 production architectures](https://pub.towardsai.net/seven-voice-ai-architectures-that-actually-work-in-production-2efaf8537bc1).

SDK facts (`evals`/`simulation` module contents, judge docstrings) were verified
directly against the installed `livekit-agents` package, not from marketing.
