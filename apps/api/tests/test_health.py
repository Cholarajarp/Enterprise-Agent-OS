"""Health check endpoint tests."""
import pytest


@pytest.mark.anyio
async def test_health_endpoint_returns_200(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_health_endpoint_structure(client):
    resp = await client.get("/health")
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert "checks" in data
    assert "version" in data


@pytest.mark.anyio
async def test_health_checks_database(client):
    resp = await client.get("/health")
    data = resp.json()
    assert "database" in data["checks"]
