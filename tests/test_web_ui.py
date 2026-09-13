import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_web_routes_are_registered():
    routes = {getattr(route, "path", None) for route in app.routes}
    assert "/login" in routes
    assert "/app" in routes
    assert "/app/stock" in routes
    assert "/app/assets" in routes


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("CSMS_WEB_DB_TESTS") != "1", reason="requires configured local PostgreSQL")
async def test_web_login_and_dashboard():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/login",
            data={"username": "dev_director", "password": os.getenv("CSMS_DEV_PASSWORD", "DevOnly123!")},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "csms_access_token" in response.cookies
        dashboard = await client.get("/app")
        assert dashboard.status_code == 200
