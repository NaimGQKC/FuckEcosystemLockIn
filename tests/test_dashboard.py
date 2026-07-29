"""Tests for the read-only call dashboard.

The properties worth pinning are about what it must NOT do: leak guest phone
numbers by default, and never expose a way to change anything.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from yen_agent.dashboard import build_app  # noqa: E402
from yen_agent.store import CallStore  # noqa: E402


@pytest.fixture
def client():
    store = CallStore(":memory:")
    store.start_call("call-1", locale="fr")
    store.end_call("call-1", outcome="completed")
    store.start_call("call-2", locale="fr")
    store.end_call("call-2", outcome="no_user_turn")
    store.record_message(call_id="call-1", kind="takeout", name="Chris",
                         phone="+15145552020", body="12 pieces de sushi")
    store.record_booking_attempt(call_id="call-1", ok=False, party_size=7,
                                 wanted_time="2026-08-01T19:00", name="Alex",
                                 phone="+15145551234", error="LargePartyError")
    yield TestClient(build_app(store))
    store.close()


def test_renders_the_things_that_need_a_human(client):
    body = client.get("/").text
    assert "Chris" in body               # the outstanding message
    assert "12 pieces de sushi" in body  # what they actually wanted
    assert "LargePartyError" in body     # the booking that failed


def test_phone_numbers_are_masked_by_default(client):
    """The owner will open this on a phone, in public."""
    body = client.get("/").text
    assert "+15145552020" not in body
    assert "2020" in body  # enough to recognise the caller


def test_full_numbers_require_an_explicit_act(client):
    body = client.get("/?full=1").text
    assert "+15145552020" in body


def test_token_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv("YEN_DASHBOARD_TOKEN", "s3cret")
    assert client.get("/").status_code == 401
    assert client.get("/?token=wrong").status_code == 401
    assert client.get("/?token=s3cret").status_code == 200


def test_no_token_configured_means_open(client):
    """Local use must not require ceremony; production sets the token."""
    assert client.get("/").status_code == 200


def test_health_is_unauthenticated_and_cheap(client, monkeypatch):
    """The host's liveness probe cannot carry a secret."""
    monkeypatch.setenv("YEN_DASHBOARD_TOKEN", "s3cret")
    r = client.get("/health")
    assert r.status_code == 200
    assert "ok" in r.text.lower()


def test_dashboard_exposes_no_mutating_routes():
    """Read-only is a security property, not a description. Libro is the record."""
    store = CallStore(":memory:")
    try:
        app = build_app(store)
        methods = set()
        for route in app.routes:
            methods |= set(getattr(route, "methods", set()) or set())
        assert methods <= {"GET", "HEAD"}, methods
    finally:
        store.close()


def test_empty_store_renders_without_error():
    """A brand-new deployment has no calls; the page must still load."""
    store = CallStore(":memory:")
    try:
        r = TestClient(build_app(store)).get("/")
        assert r.status_code == 200
        assert "No calls recorded yet" in r.text
    finally:
        store.close()
