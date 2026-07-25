# Call data: what we keep, why, and for how long

The agent now writes a durable record of every call (`store.py`). That record
contains **guest personal information** — names and phone numbers — so it needs a
stated policy rather than an accident.

Quebec's **Law 25** (Act respecting the protection of personal information in the
private sector, as amended) is the relevant regime. This document is an
engineering summary of how the system behaves, not legal advice; confirm specifics
with the restaurant before going live.

## What is stored

| Table | Contents | Contains PII? |
|---|---|---|
| `calls` | call id, timestamps, locale, outcome | Caller number, if telephony provides one |
| `messages` | name, phone, what they asked for, whether the restaurant was told | **Yes** |
| `booking_attempts` | name, phone, party size, requested time, success/failure | **Yes** |

**Not stored:** payment details (we never collect any), audio recordings, or
email content. The `transcript` column exists but the agent does not populate it
today — turning that on is a deliberate decision, not a default, because a
transcript is far more sensitive than a name and a number.

## Why we keep it

Three purposes, all narrow:

1. **Keeping a promise.** When the agent says "I've passed your message to the
   team", the record is what makes that true. Without it the message is lost —
   which is exactly the bug this replaced.
2. **Catching failures.** So the owner can see that a caller wanted a table and
   didn't get one. Silent failures are the expensive kind.
3. **Knowing it still works.** On a system meant to run unattended, the call log
   is how anyone notices it has stopped working.

## How long

**Default: 90 days** (`store.DEFAULT_RETENTION_DAYS`), then deleted.

That is a deliberate choice: long enough to investigate "what happened on that
call last month", short enough that we are not accumulating a guest contact
database nobody asked for. Libro remains the system of record for reservations —
this log is operational telemetry, not a CRM.

Purge manually or from a scheduled job:

```bash
python scripts/calls.py --purge 90
```

⚠️ **This is not automatic yet.** Nothing calls `purge_older_than` on a schedule.
Until it runs on a timer (cron, or a startup task in the agent), records accumulate
indefinitely. That is an open item, not a completed control.

## Access

- Phone numbers are **masked by default** in `scripts/calls.py` (`***-***-9000`).
  `--full-numbers` shows them, which is the point at which someone should be
  thinking about who is running the command.
- There is no web dashboard and no network listener — the log is a file on the
  server, readable by whoever has access to that box. Deliberate: fewer surfaces
  to secure on a deployment nobody intends to maintain.

## Things to settle before going live

- [ ] Confirm the retention period with the owner (90 days is our default, not their decision).
- [ ] Decide whether callers should be told the call is logged, and in what words.
- [ ] Schedule the purge so retention is enforced rather than aspirational.
- [ ] Decide whether transcripts get stored at all — currently they do not.
