import pytest
import httpx

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="session")
def token():
    resp = httpx.post(f"{BASE_URL}/api/auth/token", data={"username": "dev_director", "password": "DevOnly123!"})
    if resp.status_code == 200:
        return resp.json()["access_token"]
    return None

endpoints = [
    "/api/petty-purchases",
    "/api/indents",
    "/api/receipts",
    "/api/requisitions",
    "/api/transfers",
    "/api/stock/balances",
]

@pytest.mark.parametrize("endpoint", endpoints)
def test_unauthenticated_returns_401(endpoint):
    resp = httpx.get(f"{BASE_URL}{endpoint}")
    assert resp.status_code == 401

def test_authenticated_petty_purchases(token):
    assert token is not None
    client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    resp = client.get("/api/petty-purchases")
    assert resp.status_code != 401
