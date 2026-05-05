"""Tests for model gateway API, routing, and registry."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ruflo_model_gateway.main import create_app


@pytest.fixture
def app():
    """Create a test app instance."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create an async test client."""
    from ruflo_model_gateway.registry.store import ModelRegistryStore
    from ruflo_model_gateway.config import get_settings
    
    settings = get_settings()
    store = ModelRegistryStore(settings.registry_db_path)
    await store.initialize()
    app.state.registry = store
    app.state.settings = settings
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        
    await store.close()


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """Health endpoint returns ok."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness(client: AsyncClient):
    """Readiness endpoint returns status."""
    response = await client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_list_models(client: AsyncClient):
    """Models endpoint returns list."""
    response = await client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_register_model(client: AsyncClient):
    """Can register a model in the registry."""
    response = await client.post("/v1/models/register", json={
        "model_id": "test-model",
        "provider": "ollama",
        "display_name": "Test Model",
        "capabilities": ["coding"],
        "context_window": 8192,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "registered"


@pytest.mark.asyncio
async def test_register_and_list_model(client: AsyncClient):
    """Register then list shows the model."""
    await client.post("/v1/models/register", json={
        "model_id": "list-test-model",
        "provider": "ollama",
    })
    response = await client.get("/v1/models")
    models = response.json()["data"]
    ids = [m["id"] for m in models]
    assert "list-test-model" in ids


@pytest.mark.asyncio
async def test_deregister_model(client: AsyncClient):
    """Can remove a model from the registry."""
    await client.post("/v1/models/register", json={
        "model_id": "del-test",
        "provider": "ollama",
    })
    response = await client.delete("/v1/models/del-test")
    assert response.status_code == 200
    assert response.json()["status"] == "deregistered"
