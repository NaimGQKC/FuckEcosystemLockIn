"""LibroReservationService — the real Libro JSON:API (Phase 3).

This is the *only* new code needed to go live: same JSON:API client, real base
URL, OAuth client-credentials auth with token caching/refresh. Swapping the mock
for this is a one-line change in ``reservation.build_service`` /
``config.Settings``.

Wiring is provided and self-contained, but the real endpoints require Libro
partner credentials + staging certification, so it is exercised against staging,
not in the offline test suite.
"""

from __future__ import annotations

import time as _time

import httpx

from .jsonapi import JsonApiReservationService


class LibroReservationService(JsonApiReservationService):
    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        restaurant_id: str,
        token_url: str = "/oauth/token",
        scope: str = "bookings people availability:all",
    ):
        client = httpx.AsyncClient(base_url=base_url, timeout=15.0)
        super().__init__(client=client, restaurant_id=restaurant_id)
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope
        self._token: str | None = None
        self._token_expiry: float = 0.0

    async def _auth_headers(self) -> dict[str, str]:
        if not self._token or _time.time() >= self._token_expiry - 60:
            await self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    async def _refresh_token(self) -> None:
        resp = await self._client.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self._scope,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        # Libro tokens expire in ~7200s; respect the server's value when present.
        self._token_expiry = _time.time() + int(payload.get("expires_in", 7200))
