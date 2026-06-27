# Mock Libro contract

`mock_libro/` mirrors the subset of the Libro Reserve JSON:API that the agent
uses. It exists so Phase 1 runs end-to-end with no Libro credentials, and so the
same `ReservationService` code path is exercised against the mock and (later)
real Libro.

> **Honesty caveat.** Libro's full partner schema is only available to approved
> partners. The field names and error codes below are modeled from the brief and
> public references and are a **best-effort approximation**, not a verified
> byte-for-byte copy. Treat this as the contract our client *expects*; during
> Libro staging certification (Phase 3) reconcile any differences in the one
> place that owns the wire format — `src/yen_agent/reservation/jsonapi.py` — and
> the agent/tools above it stay unchanged.

## Conventions

- **Media type:** `application/vnd.libro-restricted-v2+json` (sent as `Accept`,
  returned as `Content-Type`).
- **Envelope:** JSON:API — `{ "data": { "type", "id", "attributes",
  "relationships" } }`; collections return a list under `data`.
- **Attribute keys:** dasherized (`first-name`, `modification-restricted`).
- **Errors:** `{ "errors": [ { "code", "status", "title", "detail" } ] }` with
  stable numeric codes.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/restricted/restaurants` | list restaurants |
| GET | `/restricted/restaurant/seatings?date=&size=&restaurant=` | availability |
| GET | `/restricted/restaurant/bookings?filter[phone]=` | list a guest's bookings |
| POST | `/restricted/restaurant/bookings` | create a booking |
| GET | `/restricted/restaurant/bookings/{id}` | fetch a booking |
| PATCH | `/restricted/restaurant/bookings/{id}` | update size/note |
| PUT | `/restricted/restaurant/bookings/{id}/reschedule` | move to a new time |
| DELETE | `/restricted/restaurant/bookings/{id}` | cancel |
| GET | `/restricted/people/{id}` | fetch a person |
| PATCH | `/restricted/people/{id}` | update a person |
| POST | `/restricted/payment-intents/initialize` | start a no-show/deposit payment |

## Availability (seatings) response

```json
{
  "data": {
    "type": "seatings",
    "id": "rest_yen_mtl:2026-07-20",
    "attributes": {
      "size": 2,
      "slots": {
        "2026-07-20": [
          {
            "time": "2026-07-20T18:00:00-04:00",
            "experience": { "id": "exp_dinner_yen", "name": "Dinner" },
            "payment-required": false,
            "arrangement": "merged",
            "tables": ["Table 4", "Table 5"],
            "seats": 8
          }
        ]
      }
    }
  }
}
```

The mock generates slots from weekday-aware services (lunch Mon–Sat, dinner
daily, each up to a last-seating time), drops past slots, and — for the requested
party size — only returns a time if the **table-assignment engine**
(`mock_libro/floorplan.py`) can seat the party there given existing bookings'
turn-time occupancy. `arrangement`/`tables`/`seats` describe how they'd be seated
(a single table or a combined one). These seating-engine fields are a mock
convenience; real Libro models availability differently, but the agent only reads
them through `ReservationService`, so the translation is contained in `jsonapi.py`.

## Booking resource

```json
{
  "data": {
    "type": "booking",
    "id": "booking_ab12cd34ef56",
    "attributes": {
      "size": 2,
      "status": "confirmed",
      "time": "2026-07-20T18:30:00-04:00",
      "duration-min": 105,
      "tables": ["Table 5"],
      "arrangement": "single",
      "note": "window seat",
      "locale": "en",
      "modification-restricted": false
    },
    "relationships": {
      "restaurant": { "data": { "type": "restaurant", "id": "rest_yen_mtl" } },
      "person":     { "data": { "type": "person", "id": "person_..." } },
      "experience": { "data": { "type": "experience", "id": "exp_dinner_yen" } }
    }
  }
}
```

`modification-restricted: true` means some changes need restaurant staff; the
agent degrades to "take a message" rather than failing the call.

## Error codes mapped to spoken responses

| Code | Meaning | Agent behavior |
|---|---|---|
| 2001 | slot unavailable | offer nearby times / another day |
| 2005 | party size out of range (e.g. 0) | re-ask the party size |
| 2006 | large party — needs staff | stop booking, take a message |
| 4001 | booking not cancelable | take a message for the team |
| 4002 | modification restricted | take a message (staff-only change) |
| 404  | not found | re-confirm the phone/name |

Mapping lives in `src/yen_agent/reservation/errors.py`
(`error_from_jsonapi`).

## What the real swap touches

Going live changes **only** configuration + the auth/base-URL in
`LibroReservationService`:

```dotenv
YEN_RESERVATION_BACKEND=libro
LIBRO_BASE_URL=https://api.staging.libro.app
LIBRO_CLIENT_ID=...
LIBRO_CLIENT_SECRET=...
LIBRO_RESTAURANT_ID=...
```

Then run the existing test/eval suite against staging and reconcile any wire
differences in `jsonapi.py`.
