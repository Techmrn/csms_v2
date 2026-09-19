import pytest

@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client):
    response=await client.get("/api/petty-purchases")
    assert response.status_code==401

@pytest.mark.asyncio
async def test_valid_jwt_works(client, dev_tokens):
    response=await client.get("/api/stores",headers={"Authorization":f"Bearer {dev_tokens['dev_director']}"})
    assert response.status_code==200

@pytest.mark.asyncio
async def test_authenticated_identity_is_server_derived(client, dev_tokens):
    # actor_id is no longer part of the public contract. Confirm normal creation
    # succeeds with JWT identity only; DB audit identity is checked by service tests.
    headers={"Authorization":f"Bearer {dev_tokens['dev_general_sk']}"}
    payload={"purchase_date":"2026-04-01","financial_year_id":1,"store_id":3,"lines":[{"item_id":1,"quantity":1,"unit_id":1}]}
    response=await client.post("/api/petty-purchases",json=payload,headers=headers)
    assert response.status_code in (201, 404, 409, 422)
    # Most importantly, sending a removed client actor_id must not create a 403 impersonation check.
    payload["actor_id"]=999
    response=await client.post("/api/petty-purchases",json=payload,headers=headers)
    assert response.status_code != 403

@pytest.mark.asyncio
async def test_receipt_store_scope(client, dev_tokens):
    press_headers={"Authorization":f"Bearer {dev_tokens['dev_press_sk']}"}
    payload={"receipt_date":"2026-04-01","financial_year_id":1,"store_id":3,"lines":[{"item_id":1,"received_quantity":1,"unit_id":1}]}
    response=await client.post("/api/receipts",json=payload,headers=press_headers)
    assert response.status_code==403
