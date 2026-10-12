"""Item 2 of the Ch24 test pyramid: a real, in-process pytest integration
suite against the booking create/read surface, using FastAPI's TestClient
(httpx against the ASGI app directly, in-process — no network, no running
container).

Run locally with:

    cd examples/24-testing/python
    uv sync
    uv run pytest -v

NOT invoked by verify.sh — see ../README.md "What runs where" for why
(symmetric with the Quarkus side's @QuarkusTest: both are build-time/local
test layers, while verify.sh's job is the live-container contract +
Newman + load layers).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

VALID_BOOKING = {
    "origin": {"unLocode": "USNYC", "name": "New York", "country": "US"},
    "destination": {"unLocode": "NLRTM", "name": "Rotterdam", "country": "NL"},
    "cargo": [
        {
            "description": "Palletized electronics",
            "type": "GENERAL",
            "dimensions": {"weightKg": 1200.5, "volumeM3": 4.2},
            "hazardous": False,
        }
    ],
    "requestedPickup": "2026-02-01",
}

BOOKING_ID_RE = re.compile(r"^bkg_[0-9A-HJKMNP-TV-Z]{26}$")


@pytest.fixture(autouse=True)
def _reset_store():
    """Each test gets a clean in-memory store — the module-level dict in
    app.store would otherwise leak state across test functions."""
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


def test_create_booking_returns_201_with_location_and_booking_body(client):
    resp = client.post("/bookings", json=VALID_BOOKING)

    assert resp.status_code == 201
    assert BOOKING_ID_RE.match(resp.json()["id"])
    assert resp.headers["location"] == f"/bookings/{resp.json()['id']}"
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["quote"] == {"currency": "USD", "amount": "3001.25"}


def test_get_booking_after_create_returns_200_with_same_booking(client):
    created = client.post("/bookings", json=VALID_BOOKING).json()

    resp = client.get(f"/bookings/{created['id']}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    assert body["origin"]["unLocode"] == "USNYC"
    assert len(body["cargo"]) == 1
    assert body["createdAt"] is not None


def test_get_booking_nonexistent_returns_404_problem_body(client):
    resp = client.get("/bookings/bkg_00000000000000000000000000")

    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["title"] == "Booking not found"
    assert body["status"] == 404


def test_create_booking_missing_cargo_returns_400_problem_body(client):
    invalid = {
        "origin": {"unLocode": "USNYC"},
        "destination": {"unLocode": "NLRTM"},
    }

    resp = client.post("/bookings", json=invalid)

    assert resp.status_code == 400
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["status"] == 400
