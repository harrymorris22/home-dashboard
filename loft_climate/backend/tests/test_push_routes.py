"""FastAPI route tests for push endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    # `with` runs the lifespan: VAPID load_or_create, push scheduler etc.
    with TestClient(app) as c:
        yield c


SAMPLE_SUB = {
    "endpoint": "https://web.push.apple.com/aBcD",
    "keys": {"p256dh": "BPubKey", "auth": "Auth"},
    "ua": "Mozilla/5.0 iPhone",
    "label": "iPhone",
}


def test_vapid_public_returns_key(client):
    resp = client.get("/api/push/vapid_public")
    assert resp.status_code == 200
    body = resp.json()
    assert "public_key" in body
    assert body["public_key"]
    assert body["subject"].startswith("mailto:")


def test_subscribe_returns_201_and_idempotent(client):
    resp = client.post("/api/push/subscribe", json=SAMPLE_SUB)
    assert resp.status_code == 201
    first = resp.json()["id"]

    resp2 = client.post("/api/push/subscribe", json=SAMPLE_SUB)
    assert resp2.status_code == 201
    # Same endpoint → upserted, same id.
    assert resp2.json()["id"] == first


def test_unsubscribe_idempotent(client):
    client.post("/api/push/subscribe", json=SAMPLE_SUB)
    resp = client.request("DELETE", "/api/push/subscribe", json={"endpoint": SAMPLE_SUB["endpoint"]})
    assert resp.status_code == 204
    # Second time on missing endpoint also 204.
    resp = client.request("DELETE", "/api/push/subscribe", json={"endpoint": SAMPLE_SUB["endpoint"]})
    assert resp.status_code == 204


def test_list_subscriptions(client):
    client.post("/api/push/subscribe", json=SAMPLE_SUB)
    resp = client.get("/api/push/subscriptions")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["ua"] == SAMPLE_SUB["ua"] for it in items)


def test_status_endpoint(client):
    resp = client.get("/api/push/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["vapid_ready"] is True
    assert body["enabled"] is True


def test_test_push_404_when_no_subscriptions(client):
    resp = client.post("/api/push/test")
    assert resp.status_code == 404


def test_snooze_roundtrip(client):
    resp = client.post("/api/push/snooze", json={"until": "2099-01-01T00:00:00+00:00"})
    assert resp.status_code == 200
    assert resp.json()["snooze_until"].startswith("2099")
    resp = client.post("/api/push/snooze", json={"until": None})
    assert resp.status_code == 200
    assert resp.json()["snooze_until"] is None
