# Connecting the agent to the real YEN reservations (Libro private API)

YEN's reservations run on **LibroReserve** (now part of OpenTable). The official
partner API route did not respond, so the live path is the **private dashboard
API** — the same REST/JSON API that `dashboard.libroreserve.com` uses, based on a
network analysis of the live session (July 2026).

Because every backend sits behind the `ReservationService` interface, supporting
this is **one adapter file** — `src/yen_agent/reservation/libro_private.py` — and
a config switch. The agent, tools, and concierge are unchanged.

## The dialect (vs. the mock)

| | Mock / partner dialect | Private dashboard dialect |
|---|---|---|
| Base URL | `api.staging.libro.app` | `https://api.libroreserve.com` |
| Auth | OAuth bearer | `Authorization: Token token="…", email="…"` (static) |
| Accept | `…libro-restricted-v2+json` | `…libro-private-v2+json` |
| Party size | `size` | `slots` |
| Availability | `GET /restricted/…/seatings` | `GET /availabilities` |
| Reservation | `booking` | `booking` (party size = `slots`) |
| Guest | `person` | `person` (`GET /people/query` to search) |
| Restaurant | rest id in path | `restaurant-id=8169` query param |

Endpoints used: `GET /ping`, `GET /availabilities`, `GET /people/query`,
`POST /people`, `POST /bookings`, `GET/PATCH /bookings/:id`.

## Security (read this)

The token is **long-lived and powerful** — it can read and write every
reservation on the account (it also authenticates the Pusher live feed). Treat it
like a password:

- It lives **only** in your local `.env` (git-ignored). Never commit it, never
  log it, never paste it into chat or a PR.
- If it may have leaked, rotate it (re-log in to the dashboard to mint a new one).
- The adapter loads it from `LIBRO_PRIVATE_TOKEN` and never prints it.

This is an **undocumented internal API**: it can change without notice (the
OpenTable migration makes that more likely). The adapter isolates every
wire-format detail so a change touches one file.

## Two remaining unknowns (and how to close them safely)

The analysis captured the endpoints and model field names, but **not** the live
request/response bodies for `/availabilities` and `POST /bookings` — capturing
those would have written to the production floor. The adapter's parsers are
therefore written to tolerate the likely key spellings, and are marked to
finalize after one capture pass.

**Step 1 — read-only probe (safe, do this first):**

```bash
# credentials go in .env, never on the command line
python scripts/probe_libro_private.py --date 2026-08-15 --party 2
```

This calls only `GET /ping` and `GET /availabilities` (and `/people/query` with
`--query`). It creates nothing. Share the printed JSON and we lock the
`/availabilities` mapping to the real field names.

**Step 2 — one controlled test booking (writes to the floor, so deliberate):**

Create a single booking for an obviously-fake guest ("ZZ Test") on a far-future,
off-peak slot while watching the network tab, to capture the exact `POST
/bookings` body — then cancel it. That confirms the create/cancel mapping. (Can
also be done end-to-end through the agent once availability is confirmed.)

## Turning it on

In `.env`:

```dotenv
YEN_RESERVATION_BACKEND=libro-private
LIBRO_PRIVATE_TOKEN=<the token — treat like a password>
LIBRO_PRIVATE_EMAIL=<your Libro login email>
LIBRO_PRIVATE_RESTAURANT_ID=8169
```

Then run the agent exactly as before (`python agent.py console`). Every booking
now lands on YEN's real Libro floor.

## Notes

- **Concurrency / double-booking:** between the availability check and the create
  call, a walk-in or another caller can take the last table. The adapter maps a
  422 to a graceful "that just filled up" so the agent offers another time rather
  than asserting a seat it doesn't have.
- **Live availability (later):** the dashboard gets real-time updates via a
  Pusher websocket (`POST /session/pusher/auth`). For a phone flow the
  check-then-book pull is sufficient; a Pusher subscription would let the agent
  react to a slot filling mid-call. Not needed for the MVP.
- **Deposits:** handled by Moneris in this dialect; the adapter currently declines
  deposit setup gracefully (not needed for the phone MVP).
