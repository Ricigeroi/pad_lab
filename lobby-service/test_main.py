import pytest
from httpx import AsyncClient
from fastapi import FastAPI
from main import app

@pytest.mark.asyncio
async def test_hello_lobby_service():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/lobby_service/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello from lobby_service"}

@pytest.mark.asyncio
async def test_get_service2_data():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/lobby_service/data")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "random" in data

@pytest.mark.asyncio
async def test_hello_lobby_service_timeout(monkeypatch):
    async def mock_hello_lobby_service():
        await asyncio.sleep(6)  # Simulate a delay longer than the timeout
        return {"message": "Hello from lobby_service"}

    monkeypatch.setattr("lobby_service.main._hello_lobby_service", mock_hello_lobby_service)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/lobby_service/hello")
    assert response.status_code == 408
    assert response.json() == {"detail": "Request Timeout"}

@pytest.mark.asyncio
async def test_get_service2_data_timeout(monkeypatch):
    async def mock_get_service2_data():
        await asyncio.sleep(6)  # Simulate a delay longer than the timeout
        return {"data": "This is some data from Service2", "random": 42}

    monkeypatch.setattr("lobby_service.main._get_service2_data", mock_get_service2_data)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/lobby_service/data")
    assert response.status_code == 408
    assert response.json() == {"detail": "Request Timeout"}