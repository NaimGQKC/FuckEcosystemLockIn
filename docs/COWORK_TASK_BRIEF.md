# Task brief for Claude Cowork (Sadie + Libro reconnaissance)

Hand this to Cowork. Tasks are ordered by value to the build. **All read-only** —
no writes to either system, and no reservations created, modified or cancelled.

**Standing rules for every task**
- Read-only. `GET` only. Never submit feedback, apply a recommendation, or save config.
- **Never include the Libro or Sadie API token** in any output file.
- **Redact guest PII** in anything written to a file: replace names with `G1, G2…`,
  phone numbers with `+1514555XXXX`, emails with `guest1@example.com`. Keep the
  *structure* — we need to see that a phone number was collected, not whose.
- Where a task says "verbatim", it means the agent/system text, not guest data.

---

## TASK 1 — The 84 call transcripts (highest value by far)

**Why:** these become our regression test suite. The teardown analysed them
statistically; we need the raw conversations so we can replay them against our agent
and diff the outcomes. This is worth more than every other task combined.

**What to do**
1. Pull all call records from `GET /api/overview/call?restaurantId=37487&from=&to=&limit=200`
   for 30 Jun – 25 Jul 2026.
2. For each call, export as JSON: `id`, `startedAt`, `callDuration`, `category`,
   `endedReason`, `transferReasonId`, `summary`, the full `transcript`, and the
   complete **`messages[]` array** (this contains tool calls, arguments, results and
   `secondsFromStart` timings — do not drop it).
3. **Redact guest PII** as above, consistently — the same guest should map to the
   same pseudonym across calls.
4. Write one file: `sadie_calls_redacted.json`.

**Also produce** `sadie_calls_summary.md` with, for each call, one line:
`#id · duration · category · outcome · what the caller wanted · where it went wrong (if it did)`.

---

## TASK 2 — The compiled system prompt, verbatim

**Why:** the teardown decomposed it section by section, but I want the raw text to
diff against ours — especially the STT phonetic-correction table and the bilingual
rules, which are the hardest-won parts.

**What to do:** from any single call record, take `messages[0]` where `role ==
"system"` and save it verbatim as `sadie_system_prompt.txt`. It's ~28,000 characters.
No redaction needed (it's venue config, not guest data), but scan it once to be sure
no phone numbers of staff are embedded — mask those if present.

---

## TASK 3 — Libro: the adjacent-day availability endpoint  ⭐ unblocks a feature

**Why:** our biggest planned feature is the "fully booked → offer another day →
capture a notify-me" cascade, which replaces a dead-end transfer. It hinges on one
endpoint we've never seen a response from.

**What to do (read-only GETs against `api.libroreserve.com`)**
1. `GET /availabilities/summary?restaurant-id=8169&from=2026-09-01&to=2026-09-14`
   — save the **full raw JSON**. We need to know whether it returns per-day status
   only (`"available"`) or actual slot counts, and whether it's party-size aware
   (try adding `&size=2` and `&slots=2` and report whether the response changes).
2. `GET /availabilities/{date}?restaurant-id=8169` for a date you can see is
   **fully or nearly booked** — I need to see what a *constrained* day looks like,
   not just a wide-open one. Empty `{}` values are the interesting part.
3. Report: does any response expose **seating areas / sections** (bar, sushi
   counter) as separate inventory? The availability map has a `seatingArea` key that
   is empty string `""` in everything we've seen — is it ever populated?

Save as `libro_availability_probe.json` + a short note on what you observed.

---

## TASK 4 — Libro: is a party of 7+ bookable at all?

**Why:** a real contradiction I can't resolve. The availability endpoint only ever
returns party sizes **1–6**, and services report `max-slots: 6` — but the venue's own
knowledge base says tables are held "2h for parties of **7+**", and Sadie's transfer
rule is ">7 → transfer", implying 7 *is* bookable.

**What to do:** in the **Libro dashboard UI** (not the API), try to create a
reservation for **7 people** and then **8 people** — *without saving*. Report:
- Does the UI allow selecting 7? 8?
- Does it show available times, or block it?
- Screenshot the party-size selector and any warning shown.

This decides whether our agent should book 7 or escalate it.

---

## TASK 5 — Libro: the Online Waiting List / "Notify Me" feature

**Why:** the destination for every "we're fully booked" caller. The teardown says
Libro ships it but it's **off by default and activated via Libro support**.

**What to do:** in the Libro dashboard, find whether a waiting list / notify-me
feature exists for venue 8169, whether it's enabled, and what it captures (name,
phone, date, party size?). Screenshot the settings screen. If there's an API surface
for it visible in the network tab while browsing that screen, capture the endpoint.

---

## TASK 6 — Sadie dashboard screenshots (for our webapp design)

**Why:** we're building the operator webapp that replaces this. I'd rather copy a
proven information architecture than invent one.

**Screens to capture (redact guest names/phones in the images):**
1. **Overview / Today** — the default landing screen
2. **Calls list** — showing the columns and filters
3. **Call detail** — especially the **transcript + tool-call inspector** panes
4. **Recommendations** — the full list, with the wording of each recommendation
5. **Working hours** — particularly the *"Sadie's Awareness"* tab (what the agent
   believes the hours to be)
6. **Booking settings** and **Transfer reasons** configuration
7. **Knowledge base** editor

For each: what's on screen, and **what an operator would actually do there daily**.

---

## TASK 7 — Verify the venue's real config values

**Why:** several of our defaults come from the teardown; I want them confirmed
rather than assumed.

Confirm from Sadie's config screens (or the config endpoints):
- Exact working hours per day, including whether Sunday lunch is genuinely closed
- `finalBookingQuestion` wording (we use "any dietary restrictions or special requests?")
- The **large-party threshold** actually configured (7? 8?)
- Whether `takeawayUrl` / `sendTakeAwaySms` are still empty/false
- The **cancellation policy** KB answer — still blank?
- The greeting text and the idle re-prompt text, verbatim, both languages

---

### What I'd skip
Billing, users/permissions, HubSpot/Stripe/Kinde internals, POS integrations,
multi-location, and anything requiring a write. None of it changes what we build.
