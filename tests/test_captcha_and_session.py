import os
import time
import hmac
import hashlib
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.security.captcha import generate_numeric_captcha, verify_numeric_captcha, CAPTCHA_VALIDITY_SECONDS
from app.core.config import get_settings


def test_captcha_generation_and_verification():
    data = generate_numeric_captcha()
    digits = data["digits"]
    token = data["token"]
    svg = data["svg"]

    assert len(digits) == 5
    assert digits.isdigit()
    assert "<svg" in svg
    assert "</svg>" in svg
    assert len(token) > 20

    # Verification with correct digits
    assert verify_numeric_captcha(digits, token) is True

    # Verification with wrong digits
    assert verify_numeric_captcha("00000", token) is False

    # Verification with tampered token
    assert verify_numeric_captcha(digits, token + "x") is False
    assert verify_numeric_captcha(digits, "invalid:token") is False

    # Expired token
    settings = get_settings()
    expired_timestamp = int(time.time()) - 400  # Older than 300 seconds
    payload = f"12345:{expired_timestamp}"
    sig = hmac.new(settings.jwt_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    expired_token = f"{payload}:{sig}"
    assert verify_numeric_captcha("12345", expired_token) is False


@pytest.mark.asyncio
async def test_captcha_api_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/captcha")
        assert res.status_code == 200
        data = res.json()
        assert "svg" in data
        assert "token" in data
        assert "<svg" in data["svg"]
        assert len(data["token"]) > 20


@pytest.mark.asyncio
async def test_login_page_renders_captcha_and_cache_headers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/login")
        assert res.status_code == 200
        assert "captcha_token" in res.text
        assert "captcha_input" in res.text
        assert "no-store" in res.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_login_post_requires_valid_captcha():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid captcha
        res = await client.post(
            "/login",
            data={
                "username": "dev_director",
                "password": "Password@1",
                "captcha_token": "fake_token",
                "captcha_input": "99999",
            },
            follow_redirects=False,
        )
        assert res.status_code == 400
        assert "Invalid or expired security numbers" in res.text


@pytest.mark.asyncio
async def test_logout_clears_site_data_and_cookies():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/logout", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers.get("location") == "/login"
        # Verify Clear-Site-Data header
        assert "Clear-Site-Data" in res.headers
        clear_data = res.headers["Clear-Site-Data"]
        assert "cache" in clear_data
        assert "cookies" in clear_data
        # Verify Cache-Control
        assert "no-store" in res.headers.get("Cache-Control", "")
