import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def get_all_paths(routes, prefix=""):
    paths = set()
    for r in routes:
        if hasattr(r, "path") and r.path is not None:
            paths.add(prefix + r.path)
        if hasattr(r, "routes"):
            p = prefix + (getattr(r, "prefix", "") or "")
            paths.update(get_all_paths(r.routes, p))
        elif hasattr(r, "original_router"):
            p = prefix + (getattr(r.include_context, "prefix", "") or "")
            paths.update(get_all_paths(r.original_router.routes, p))
    return paths


@pytest.mark.asyncio
async def test_web_routes_are_registered():
    routes = get_all_paths(app.routes)
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
            data={"username": "dev_director", "password": os.getenv("CSMS_DEV_PASSWORD", "Password@1")},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "csms_access_token" in response.cookies
        dashboard = await client.get("/app")
        assert dashboard.status_code == 200
