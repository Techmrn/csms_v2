import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_web_routes_are_registered():
    from starlette.routing import Mount, Route
    def get_routes(routes, prefix=""):
        result = set()
        for route in routes:
            if hasattr(route, "path") and hasattr(route, "endpoint"):
                result.add(prefix + route.path)
            if hasattr(route, "routes"):
                p = getattr(route, "path", "") or ""
                result.update(get_routes(route.routes, prefix + p))
            elif hasattr(route, "original_router") and hasattr(route.original_router, "routes"):
                p = getattr(route, "path", "") or getattr(getattr(route, "include_context", None), "prefix", "") or ""
                result.update(get_routes(route.original_router.routes, prefix + p))
        return result
        
    routes = get_routes(app.routes)
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
