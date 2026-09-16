import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
import httpx

@pytest_asyncio.fixture
async def client():
    transport=ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def dev_tokens(client):
    users=["dev_director","dev_deputy","dev_general_sk","dev_assistant_sk","dev_press_head","dev_press_sk"]
    tokens={}
    for username in users:
        response=await client.post("/api/auth/token", data={"username":username,"password":"Password@1"})
        if response.status_code==200:
            tokens[username]=response.json()["access_token"]
    return tokens

