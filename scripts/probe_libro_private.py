"""READ-ONLY probe of the Libro private API — confirms the reverse-engineered shapes.

The technical analysis captured endpoints and model field names, but NOT the live
request/response bodies for `/availabilities` and `/bookings` (capturing those
would have written to the production floor). This script fills that gap using
ONLY safe, read-only GET calls:

    GET /ping
    GET /availabilities?restaurant-id=&started-on=&slots=
    GET /people/query?query=<text>        (optional; needs --query)

It NEVER creates, updates, or cancels anything. It prints the raw JSON so we can
finalize the field mappings in libro_private.py.

Usage (PowerShell / bash), with credentials in your .env (never on the CLI):

    python scripts/probe_libro_private.py --date 2026-08-15 --party 2
    python scripts/probe_libro_private.py --date 2026-08-15 --party 2 --query "514"

Required in .env:
    LIBRO_PRIVATE_TOKEN=...          # the Token value (treat like a password)
    LIBRO_PRIVATE_EMAIL=<your Libro login email>
    LIBRO_PRIVATE_RESTAURANT_ID=8169
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

ACCEPT = "application/vnd.libro-private-v2+json"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _pretty(label: str, status: int, body) -> None:
    print(f"\n=== {label}  (HTTP {status}) ===")
    try:
        print(json.dumps(body, indent=2, ensure_ascii=False)[:4000])
    except (TypeError, ValueError):
        print(str(body)[:2000])


async def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Read-only Libro private API probe.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD to check availability for")
    parser.add_argument("--party", type=int, default=2, help="party size (slots)")
    parser.add_argument("--query", default="", help="optional guest search term (name/phone)")
    parser.add_argument("--base-url", default=os.environ.get(
        "LIBRO_PRIVATE_BASE_URL", "https://api.libroreserve.com"))
    args = parser.parse_args()

    token = os.environ.get("LIBRO_PRIVATE_TOKEN", "")
    email = os.environ.get("LIBRO_PRIVATE_EMAIL", "")
    restaurant_id = os.environ.get("LIBRO_PRIVATE_RESTAURANT_ID", "8169")

    if not token or not email:
        print("ERROR: set LIBRO_PRIVATE_TOKEN and LIBRO_PRIVATE_EMAIL in .env first.")
        print("       (Never put the token on the command line or in a commit.)")
        return 1

    import httpx

    headers = {
        "Accept": ACCEPT,
        "Authorization": f'Token token="{token}", email="{email}"',
    }
    print(f"Probing {args.base_url} as {email} (restaurant {restaurant_id}) — READ ONLY.")

    async with httpx.AsyncClient(base_url=args.base_url, headers=headers, timeout=20) as client:
        # 1) liveness + auth
        try:
            r = await client.get("/ping")
            _pretty("GET /ping", r.status_code, _safe_json(r))
            if r.status_code in (401, 403):
                print("\n>>> Auth rejected. Re-check the token/email in .env.")
                return 1
        except Exception as exc:
            print(f"Could not reach {args.base_url}: {type(exc).__name__}: {exc}")
            return 1

        # 2) availability — the key unknown
        r = await client.get("/availabilities", params={
            "restaurant-id": restaurant_id,
            "started-on": args.date,
            "slots": args.party,
        })
        _pretty(f"GET /availabilities ({args.date}, party {args.party})", r.status_code, _safe_json(r))

        # 3) optional guest search
        if args.query:
            r = await client.get("/people/query", params={"query": args.query})
            _pretty(f"GET /people/query?query={args.query}", r.status_code, _safe_json(r))

    print("\nDone. Nothing was created or modified. Share the JSON above to finalize")
    print("the field mappings in src/yen_agent/reservation/libro_private.py.")
    return 0


def _safe_json(resp):
    try:
        return resp.json()
    except ValueError:
        return resp.text


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
