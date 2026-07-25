# What this costs to run, per month

Recalculated after two changes that moved the numbers: French TTS is no longer
Deepgram, and we now know the real per-turn token count.

## The volume, from real data (not a guess)

The venue's own call log: **84 calls in 26 days ≈ 97 calls/month**, median **54
seconds**, p90 119s. That works out to roughly **90 talk-minutes/month**.

Everything below scales off that.

## Monthly estimate

| Component | Basis | Est. |
|---|---|---|
| Twilio phone number | ~$1.15/mo + ~$0.0085/min inbound × 90 | **~$2** |
| Deepgram STT (Nova-3) | ~$0.0077/min streaming × 90 | **~$0.70** |
| **TTS (multilingual, French)** | agent speaks ~40% of airtime ≈ 36 min, at ElevenLabs-class rates | **~$3–6** |
| LLM (Groq 70B, paid) | ~3,450 tok/turn × ~8 turns × 97 calls ≈ 2.7M input tok | **~$2** |
| LiveKit Cloud | free tier likely covers this volume | **$0–5** |
| Hosting (small VPS, persistent disk) | fixed | **~$5–6** |
| **Total** | | **~$13–22/mo** |

## What changed, and why

**TTS roughly tripled — and it was not optional.** We had budgeted Deepgram
Aura-2 at ~$0.018/min for both languages. Then verification showed **all 58 Aura
voices are English-only**. At a venue where two-thirds of calls are French, an
English voice mangling *"bonjour"* defeats the entire French-first design. So
multilingual mode routes to an ElevenLabs-class voice via LiveKit Inference.

This is the **single largest line item after hosting**, and it is the one to
re-check if volume grows. At 97 calls/month it is a few dollars; at 1,000 it
would dominate.

**The LLM number is now grounded.** Our fixed per-turn prompt was *measured* at
~3,450 tokens (system prompt ~1,995 + 9 tool schemas ~1,457). That is what makes
the free tier unusable — 12,000 TPM allows ~3.5 requests/min when a live call
needs 6–12 — and it is also what sets the paid cost. **Trimming that prompt is
the one lever that reduces cost and latency simultaneously, on any provider.**

## Honesty about these numbers

- **The TTS figure is the least certain.** LiveKit Inference pricing is bundled
  and we have not been billed once. Treat $3–6 as a bracket, not a quote.
- **Nothing here has been measured on a real bill.** These are unit rates ×
  measured volume. The first month of real usage is the real number.
- Fixed costs (number + hosting ≈ $7–8) are **over half the total** at this
  volume. Usage barely matters; this is essentially a flat-fee system.

## The comparison that actually matters

A managed platform (Vapi-class) at ~$0.05/min platform fee plus model costs lands
in a **similar place** at 90 minutes/month — call it $10–15.

**So the cost case is a wash, and pretending otherwise is easy to pick apart.**
The reasons to own this stack are control, data ownership, and being able to fix
the Libro integration when their private API shifts — which it will. Not savings.

Where owning it *does* win is at growth: our marginal cost per extra call is
pennies of usage, while a per-minute platform fee scales linearly forever.
