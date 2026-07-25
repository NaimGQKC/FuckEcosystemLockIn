# The platform, not just the agent — what we actually need to build

Research: 24 Jul 2026. Derived from what Sadie and Slang.ai expose to operators.

The voice loop is the **engine**. What a restaurant *buys* is the **platform**
around it. Today we have a world-class engine and **zero operator surface**: the
owner cannot see a call, read a transcript, change opening hours, or know whether
the thing is working without reading Python. That is the real gap.

---

## 1. What the incumbents actually put in front of an operator

Consolidated from Sadie (heysadie.ai / Now Book It) and Slang.ai:

### A. Analytics dashboard
- Call **volume** and **answer rate**
- **Peak call times**
- **Reservations made / covers booked**
- **Revenue attribution** (Sadie)
- **Common inquiries**, categorized, with category-level filtering
- **Guest satisfaction / sentiment** scores
- Slang: caller demographic insights
- Sadie: a **natural-language reporting assistant** — ask a question, get a chart

### B. Call log
- **Full transcript** of every call
- **Sentiment** per call
- **Outcome** (booked / message taken / transferred / abandoned)
- **Voicemail summaries** (Sadie add-on)

### C. No-code configuration — the owner edits this, not a developer
- **Opening hours** (uploaded/edited in UI)
- **Menu information**
- **Greeting wording**
- **Voice + accent selection** to match brand personality
- FAQ / policies / allergy information
- **Reservation rules**
- **Escalation paths**

### D. Routing & staff alerts
- **Live transfer** to a human
- **Custom routing** — VIPs straight to staff/concierge (Slang)
- **Real-time alerts** to staff for high-priority topics: private dining, guest
  complaints, lost items (Slang)

### E. Integrations
- Reservations: Libro, Now Book It, OpenTable, SevenRooms, Tripleseat, Yelp
- POS (order injection), payments (**card capture by SMS link**), catering/event intake

### F. Multi-location
- Per-location hours, menus, reservation rules, escalation paths
- **Cross-location overflow**: if one venue is full, suggest another in the group
- Standardized phone experience across a franchise

### G. Scale
- Sadie: 20 concurrent calls · Slang: up to 1,000

---

## 2. Honest gap analysis

| Capability | Us today |
|---|---|
| Voice loop (STT/LLM/TTS, tools) | ✅ working |
| Reservation create/cancel on real Libro | ✅ proven |
| Table/slot reasoning | ✅ (mock) / Libro handles it live |
| **Call transcript stored anywhere** | ❌ nothing persists |
| **Call outcome / analytics** | ❌ none |
| **Owner-editable config** | ❌ hours & FAQ are Python constants |
| **Messages reaching a human** | ❌ `take_message` writes to an in-memory list that dies with the process |
| **Live transfer** | ❌ |
| **Staff alerts** | ❌ |
| **Any UI at all** | ❌ |
| Multi-location | ❌ (not needed for YEN) |
| Concurrency proven | ❌ never run 2 calls |

The most damning one: **`take_message` currently loses the message.** A caller is
told "I've passed this to the team" and nothing is passed to anyone. That's a
correctness bug with a customer-facing promise attached, and it's P0.

---

## 3. What we should build (and deliberately not build)

We are not going to rebuild Sadie. We need the **minimum operator surface** that
makes this (a) honest, (b) usable by a non-developer, (c) demoable as a product.

### Phase A — makes it truthful and usable *(highest value, small effort)*

1. **Persist every call.** SQLite table: id, started/ended, direction, caller phone,
   full transcript, outcome enum (`booked` / `cancelled` / `message` / `faq_only` /
   `abandoned` / `transferred`), booking id, duration, per-stage latency, token +
   minute cost.
2. **Make `take_message` actually deliver** — write to the DB *and* send (email via
   SMTP or SMS via Twilio) to an address the owner configures. Until delivery
   exists, the agent should not claim it passed the message on.
3. **Move config out of code** into a single `yen.yaml`: hours, last seating, FAQ
   answers, greeting, party-size cap, escalation contact, language mode. Owner edits
   one readable file; no Python, no redeploy logic. (This also directly answers the
   owner questionnaire — the answers land in this file.)

### Phase B — makes it a product *(the demo differentiator)*

4. **Operator web view** (FastAPI + a single HTML page — we already run FastAPI for
   the mock): list of calls, click for transcript, outcome badges, and a small
   stats strip (calls today, bookings made, messages taken, avg handle time,
   estimated cost). This is what turns "a script" into "a product" at the meetup.
5. **Live transfer to a human** during opening hours — Sadie has it on *every* tier;
   it's table stakes.
6. **SMS/email confirmation to the guest** after booking.

### Phase C — scale/polish *(only if it's going somewhere real)*
7. Sentiment + auto-categorized inquiry topics (feeds the analytics view).
8. Staff alerts for complaints / large parties / private dining.
9. Concurrency test, then multi-location config if ever needed.

### Explicitly NOT building
- POS/order injection (out of scope — YEN is reservations)
- Payments / card capture
- Revenue attribution, demographics (needs data we won't have)
- Franchise/multi-location (single venue)

---

## 4. Why this ordering

Phase A is mostly **correctness**, not features: right now the agent makes promises
the system doesn't keep (messages) and can't be configured by the person who owns
the facts (hours). Those are the things that would embarrass us in front of the
owner.

Phase B is what makes the difference between *"I built a voice bot"* and *"here's
the product"* — and the call log with transcripts is also our **eval corpus**, which
feeds directly into the `simulation.Scenario` work from the competitive research.

One reusable insight: nearly every operator-facing feature above is downstream of
**one decision — persist the call**. Transcript, analytics, sentiment, outcomes,
eval corpus, and cost tracking all fall out of having a `calls` table. That's why
it's item #1.
