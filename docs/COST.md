# What this costs, and what it costs to *manage*

Recomputed from the venue's real call log, with published vendor rates. The
owner's constraint drives the design: **"I just want to manage the connection to
Libro. Nothing else. And it should work properly enough."**

That is a stronger requirement than low cost, and it changes the stack.

## Volume — measured, not estimated

Every duration in the 84-call log was summed directly:

```
calls in window     84  over 25.0 days   -> 102 calls/month
total talk time     91.0 min / 25 days   -> 111 min/month
median              54s      (matches the source's stated 54s)
p90                 119s     (matches the source's stated 119s)
mean                65s
```

The median and p90 reproducing the source exactly is the check that the
transcription is right. **111 talk-minutes/month** is the number everything
scales off — my earlier 90 was low.

Also worth noting: **16 of 84 calls had zero user turns.** Those still cost
telephony and a little STT, but no LLM and almost no TTS.

## What the incumbent charges: ~$250/month

For 102 calls. That is **~$2.45 per call**, or **~$2.25 per talk-minute** — for a
system where, on its own data, 43% of calls end in a transfer to a human and only
15% produce a booking.

## What ours costs

Rates are published list prices (see sources at the bottom); **none of this has
been on a real bill yet.**

| Component | Rate | Monthly at 111 min |
|---|---|---|
| LiveKit agent hosting | $0.01/agent-session-min | **$1.11** — *free tier includes 1,000 min* |
| STT (Deepgram Nova-3, via Inference) | $0.0077/min | **$0.85** |
| LLM (Gemini 2.5 Flash, via Inference) | $0.0013/min | **$0.14** |
| TTS (**Cartesia Sonic**, via Inference) | $0.03/min × ~44 min spoken | **$1.32** |
| Twilio 514 number | $1.15/mo + ~$0.0085/min | **~$2.10** |
| **Total** | | **~$5.50/month** |

The LiveKit **Build** tier is free and includes 1,000 agent minutes, 5,000 WebRTC
minutes, and **$2.50/month of Inference credit** — which covers most of the
$2.31 of STT+LLM+TTS above. Realistically this runs at **$2–6/month**.

**That is roughly 40–100× cheaper than $250/month.**

### The caveat that could change it

LiveKit's docs say that **on paid plans "agents are always warm and ready"** —
which implies free-tier agents may **cold-start**. On a restaurant phone line a
cold start means dead air on the first call of the day, and dead air at the start
of a call is precisely what produces the 19% zero-turn abandonment we are trying
to fix.

If warm agents turn out to require the **Ship** tier, that is **$50/month**, and
the total becomes **~$55/month**. Still **4.5× cheaper than $250**, and it buys
away all server management.

**This is the single number worth confirming with LiveKit before launch.** Both
outcomes are a large win; it only changes whether the answer is "$5" or "$55".

## The reversal: Cartesia comes back

I removed Cartesia earlier, arguing "one vendor, one key, one bill." Two things
since have made that wrong:

1. **Deepgram TTS cannot speak French at all** (all 58 Aura voices end in `-en`),
   so the "one vendor covers both languages" premise was false.
2. Via **LiveKit Inference, Cartesia needs no separate account or key** — it is
   billed through LiveKit. The extra-credential objection disappears.

And the cost difference is large:

| French-capable TTS | Rate | Monthly (~44 min) |
|---|---|---|
| **Cartesia Sonic** | $0.03/min | **$1.32** |
| ElevenLabs Multilingual v2 | $0.18/min | $7.92 |

ElevenLabs is **6× the price** for the same job. Cartesia also advertises
sub-100ms latency, which matters more here than marginal voice quality.

**Decision: Cartesia Sonic for French, via LiveKit Inference.** Quality still has
to be confirmed by ear before launch — neither voice has been heard yet.

## The part the owner actually cares about: management burden

This is what re-shaped the stack.

### Before (what we had built)

| Thing to manage | Why it's work |
|---|---|
| A VPS | OS patches, disk, reboots, "why is it down" |
| Deepgram account + key | rotation, billing, expiry |
| Groq account + key | rotation, billing, expiry |
| LiveKit account + key | |
| Twilio account + key | |
| SQLite on a persistent volume | backups, disk filling |
| **Libro** | ← *the only one he wants* |

**Seven things. Six of them unwanted.**

### After

| Thing to manage | |
|---|---|
| **LiveKit** — hosts the agent *and* provides STT/LLM/TTS on one key | one account, one bill |
| **Twilio** — the phone number only | one account, set once |
| **Libro** | ← the one he signed up for |

**Three things.** No server to patch, no OS, no Docker host, no scaling, no
certificates. LiveKit Cloud handles agent lifecycle, upgrades and isolation.

### The one genuine casualty: our SQLite call log

LiveKit Cloud agents run on **ephemeral storage**. Our `store.py` explicitly
requires a persistent volume — on ephemeral disk, every restart silently drops
the messages the agent promised to pass on, which is exactly the bug that module
was written to fix.

So moving to LiveKit Cloud forces a decision:

**Option A — push, don't store.** Messages, takeout requests and callbacks go out
by SMS/email *the moment they are captured*, and delivery success is what makes
the promise true. No database at all. Libro remains the record for reservations.
*Cost: you lose "show me every call from last week" and the failed-booking log.*

**Option B — a managed SQLite (e.g. Turso/libSQL).** Drop-in for our existing
code, generous free tier, nothing to run. *Cost: one more account — but zero
maintenance.*

**Recommendation: A now, B if the owner ever asks for history.** A is fewer moving
parts and directly serves "don't make me manage anything"; the SMS thread on the
manager's phone becomes the log. B stays cheap to add later because the storage
is already behind one module.

## Honesty

- **Nothing here has been billed yet.** These are list rates × measured volume.
- The cold-start question is unresolved and is the only thing that moves the
  total materially.
- Cartesia's French has not been heard by anyone on this project.
- The $250 figure is the owner's recollection, and he is currently on a free
  trial — worth confirming against an actual invoice before it is quoted anywhere.

## Sources

- [LiveKit pricing](https://livekit.com/pricing) · [Agents on LiveKit Cloud](https://livekit.com/products/agent-cloud-deployment) · [Deploy and scale agents](https://livekit.com/blog/deploy-and-scale-agents-on-livekit-cloud)
- [Deepgram pricing 2026](https://texttolab.com/blog/deepgram-pricing)
- [LiveKit Inference rates](https://www.cekura.ai/blogs/livekit-pricing)
