"""Look at what the voice agent actually did. No dashboard, no login, no server.

    python scripts/calls.py                 # summary of the last 7 days
    python scripts/calls.py --messages      # messages/waitlist nobody has actioned
    python scripts/calls.py --failed        # bookings the agent could NOT make
    python scripts/calls.py --calls         # recent calls
    python scripts/calls.py --days 30       # widen the window
    python scripts/calls.py --purge 90      # delete records older than 90 days

Why a CLI and not a web dashboard: the goal is deploy-once-and-forget. A
dashboard is a thing to host, secure, and keep running. Staff don't need one —
Libro is still the system of record for reservations. This exists to answer one
question: *did the agent do the right thing, and did anything get dropped?*
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from yen_agent.store import CallStore  # noqa: E402


def _mask(phone: str) -> str:
    """Show enough to recognise a caller, not enough to leak a list."""
    return f"***-***-{phone[-4:]}" if len(phone) >= 4 else phone


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect the voice agent's call log")
    ap.add_argument("--db", default="", help="path to the call log (default $YEN_DB_PATH)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--messages", action="store_true",
                    help="messages/waitlist the restaurant has NOT been told about")
    ap.add_argument("--failed", action="store_true",
                    help="booking attempts that failed")
    ap.add_argument("--calls", action="store_true", help="recent calls")
    ap.add_argument("--full-numbers", action="store_true",
                    help="show unmasked phone numbers (contains guest PII)")
    ap.add_argument("--purge", type=int, metavar="DAYS",
                    help="delete records older than DAYS (data retention)")
    args = ap.parse_args()

    store = CallStore(args.db)
    show = (lambda p: p) if args.full_numbers else _mask

    if args.purge is not None:
        n = store.purge_older_than(args.purge)
        print(f"Deleted {n} records older than {args.purge} days.")
        return 0

    if args.messages:
        pending = store.pending_messages()
        if not pending:
            print("Nothing outstanding — every message has been passed on.")
            return 0
        print(f"{len(pending)} message(s) the restaurant has NOT been told about:\n")
        for m in pending:
            print(f"  [{m.created_at}] {m.kind.upper()}  {m.name}  {show(m.phone)}")
            if m.body:
                print(f"      {m.body}")
            if m.party_size or m.wanted_date:
                print(f"      party of {m.party_size} — {m.wanted_date} {m.wanted_time}".rstrip())
            print()
        return 0

    if args.failed:
        rows = store.failed_bookings(since_days=args.days)
        if not rows:
            print(f"No failed bookings in the last {args.days} days.")
            return 0
        print(f"{len(rows)} booking(s) the agent could NOT complete:\n")
        for r in rows:
            print(f"  [{r['created_at']}] {r['name']} {show(r['phone'])} "
                  f"party of {r['party_size']} at {r['wanted_time']}")
            print(f"      reason: {r['error']}\n")
        return 0

    if args.calls:
        for r in store.recent_calls():
            print(f"  [{r['started_at']}] {r['call_id']}  {r['outcome']}")
        return 0

    s = store.stats(since_days=args.days)
    print(f"Last {args.days} days")
    print(f"  calls                 {s['calls']}")
    print(f"  bookings made         {s['bookings_ok']}")
    print(f"  bookings FAILED       {s['bookings_failed']}")
    print(f"  messages taken        {s['messages']}")
    print(f"  NOT yet passed on     {s['undelivered']}")
    if s["bookings_failed"]:
        print("\n  -> see details:  python scripts/calls.py --failed")
    if s["undelivered"]:
        print("  -> action needed: python scripts/calls.py --messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
