"""Shared test fixtures for the Enterprise Agent OS API test suite."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


TEST_ORG_ID = "019690a1-0000-7000-8000-000000000001"
TEST_USER_ID = "019690a1-0000-7000-8000-000000000002"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP client that talks to the FastAPI app in-process."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["X-Org-ID"] = TEST_ORG_ID
        yield ac


@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def sample_workflow():
    return {
        "id": str(uuid.uuid4()),
        "org_id": TEST_ORG_ID,
        "name": "Test Workflow",
        "slug": "test-workflow",
        "version": 1,
        "status": "draft",
        "definition": {"steps": [], "edges": []},
    }


@pytest.fixture
def sample_run(sample_workflow):
    return {
        "id": str(uuid.uuid4()),
        "org_id": TEST_ORG_ID,
        "workflow_id": sample_workflow["id"],
        "status": "queued",
        "trigger_type": "manual",
        "steps_completed": 0,
        "total_cost_usd": 0,
    }
