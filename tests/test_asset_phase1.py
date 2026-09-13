import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.category import Category
from app.models.unit import Unit
from app.models.asset import Asset, AssetMovement

from httpx import AsyncClient, ASGITransport

@pytest_asyncio.fixture(scope="module")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture(scope="module")
async def setup_items():
    async with AsyncSessionLocal() as session:
        cat_con = await session.scalar(select(Category).where(Category.type == "CONSUMABLE"))
        cat_asset = await session.scalar(select(Category).where(Category.type == "ASSET"))
        unit = await session.scalar(select(Unit).limit(1))
        
        import uuid
        suffix = str(uuid.uuid4())[:8]
        con_item = Item(code=f"TEST-CON-{suffix}", name=f"Test Consumable {suffix}", category_id=cat_con.id, unit_id=unit.id, is_active=True)
        asset_item = Item(code=f"TEST-ASS-{suffix}", name=f"Test Asset {suffix}", category_id=cat_asset.id, unit_id=unit.id, is_active=True)
        
        session.add(con_item)
        session.add(asset_item)
        await session.commit()
        
        return {"con_item_id": con_item.id, "asset_item_id": asset_item.id, "unit_id": unit.id}

@pytest_asyncio.fixture(scope="module")
async def auth_headers(client):
    response = await client.post("/api/auth/token", data={"username": "dev_general_sk", "password": "DevOnly123!"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

@pytest.mark.asyncio
async def test_unauthenticated_asset_register(client):
    response = await client.get("/api/assets")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_wrong_store_authenticated_user(client):
    response = await client.post("/api/auth/token", data={"username": "dev_press_sk", "password": "DevOnly123!"})
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    
    response = await client.get("/api/assets?store_id=1", headers=headers)
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_asset_receipt_workflow(client, setup_items, auth_headers):
    # 3. Mixed consumable + asset receipt
    con_id = setup_items["con_item_id"]
    asset_id = setup_items["asset_item_id"]
    unit_id = setup_items["unit_id"]
    
    payload = {
        "receipt_date": "2026-04-15",
        "financial_year_id": 1,
        "store_id": 1,
        "lines": [
            {
                "item_id": con_id,
                "received_quantity": 10,
                "accepted_quantity": 10,
                "rejected_quantity": 0,
                "unit_id": unit_id,
            },
            {
                "item_id": asset_id,
                "received_quantity": 2,
                "accepted_quantity": 2,
                "rejected_quantity": 0,
                "unit_id": unit_id,
                "asset_details": [
                    {"serial_no": f"SN-001-{asset_id}", "model": "M1"},
                    {"model": "M2"} # without serial number
                ]
            }
        ]
    }
    
    # Create receipt
    resp = await client.post("/api/receipts", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    receipt_id = resp.json()["id"]
    
    # Verify receipt
    resp = await client.post(f"/api/receipts/{receipt_id}/verify", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    
    # Post receipt
    resp = await client.post(f"/api/receipts/{receipt_id}/post", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    
    # Check if assets are created
    async def check_assets():
        async with AsyncSessionLocal() as session:
            assets = (await session.scalars(select(Asset).where(Asset.item_id == asset_id))).all()
            assert len(assets) == 2
            assert any(a.serial_no == f"SN-001-{asset_id}" for a in assets)
            assert any(a.serial_no is None for a in assets)
            for a in assets:
                assert a.status == "IN_STOCK"
                
                # Check AssetMovement
                movs = (await session.scalars(select(AssetMovement).where(AssetMovement.asset_id == a.id))).all()
                assert len(movs) == 1
                assert movs[0].movement_type == "RECEIPT"
                
    await check_assets()
