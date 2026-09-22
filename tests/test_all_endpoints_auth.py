import pytest

endpoints = [
    "/api/petty-purchases",
    "/api/indents",
    "/api/receipts",
    "/api/requisitions",
    "/api/transfers",
    "/api/stock/balances",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", endpoints)
async def test_unauthenticated_returns_401(client, endpoint):
    resp = await client.get(endpoint)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_petty_purchases(client, dev_tokens):
    token = dev_tokens.get("dev_director")
    assert token is not None
    resp = await client.get("/api/petty-purchases", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code != 401

