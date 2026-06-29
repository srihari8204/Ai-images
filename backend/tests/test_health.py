"""Liveness/readiness probe behaviour (monitoring task 11.4)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_healthz_always_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_flips_on_dependency_outage(client, monkeypatch):
    # All dependencies down → readiness must report 503 so traffic stops routing.
    import app.modules.monitoring.router as mon

    async def _db_down():
        return False

    async def _redis_down():
        return False

    monkeypatch.setattr(mon, "_check_db", _db_down)
    monkeypatch.setattr(mon, "redis_health_check", _redis_down)
    monkeypatch.setattr(mon.object_store, "health_check", lambda: False)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["postgres"] is False
