import asyncio
import httpx
import sys
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.category import Category
from app.models.unit import Unit
from app.models.asset import Asset, AssetMovement
from app.models.stock import StockMovement

BASE_URL = "http://localhost:8000"

async def main():
    async with AsyncSessionLocal() as session:
        cat_con = await session.scalar(select(Category).where(Category.type == "CONSUMABLE"))
        cat_asset = await session.scalar(select(Category).where(Category.type == "ASSET"))
        unit = await session.scalar(select(Unit).limit(1))
        
        con_item = await session.scalar(select(Item).where(Item.code == "TEST-CON-1"))
        asset_item = await session.scalar(select(Item).where(Item.code == "TEST-ASS-1"))
        con_id = con_item.id
        asset_id = asset_item.id
        unit_id = unit.id

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.post("/api/auth/token", data={"username": "dev_general_sk", "password": "DevOnly123!"})
        token_gsk = resp.json()["access_token"]
        headers_gsk = {"Authorization": f"Bearer {token_gsk}"}

        print("Testing Mixed consumable + asset receipt")
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
                        {"serial_no": "SN-MIX-NEW-1", "model": "M1"},
                        {"model": "M2"}
                    ]
                }
            ]
        }
        resp = await client.post("/api/receipts", json=payload, headers=headers_gsk)
        if resp.status_code != 201:
            print("FAIL: Could not create receipt:", resp.text)
            sys.exit(1)
        receipt_id = resp.json()["id"]

        resp = await client.post(f"/api/receipts/{receipt_id}/verify", headers=headers_gsk)
        if resp.status_code != 200:
            print("FAIL: Could not verify receipt:", resp.text)
            sys.exit(1)

        resp = await client.post(f"/api/receipts/{receipt_id}/post", headers=headers_gsk)
        if resp.status_code != 200:
            print("FAIL: Could not post receipt:", resp.text)
            sys.exit(1)

        print("Checking DB for assets and stock movements")
        async with AsyncSessionLocal() as session:
            assets = (await session.scalars(select(Asset).where(Asset.item_id == asset_id))).all()
            sn_assets = [a for a in assets if a.serial_no == "SN-MIX-NEW-1"]
            if not sn_assets:
                print("FAIL: Asset with serial_no SN-MIX-NEW-1 not found.")
                sys.exit(1)
                
            for a in sn_assets:
                if a.status != "IN_STOCK":
                    print("FAIL: Asset status is not IN_STOCK.")
                    sys.exit(1)
                movs = (await session.scalars(select(AssetMovement).where(AssetMovement.asset_id == a.id))).all()
                if not movs:
                    print("FAIL: AssetMovement not created.")
                    sys.exit(1)
                if movs[0].movement_type != "RECEIPT":
                    print("FAIL: AssetMovement type is not RECEIPT.")
                    sys.exit(1)
                    
            stock_movs = (await session.scalars(select(StockMovement).where(StockMovement.reference_no == f"REC-{receipt_id:06d}"))).all()
            if not any(sm.item_id == con_id for sm in stock_movs):
                print("FAIL: Consumable StockMovement not created.")
                sys.exit(1)
            if any(sm.item_id == asset_id for sm in stock_movs):
                print("FAIL: Asset StockMovement created, but it shouldn't be.")
                sys.exit(1)

        print("Testing Duplicate serial number rejected")
        payload["lines"][1]["asset_details"] = [
            {"serial_no": "SN-DUP-NEW", "model": "M1"},
            {"serial_no": "SN-DUP-NEW", "model": "M2"}
        ]
        resp = await client.post("/api/receipts", json=payload, headers=headers_gsk)
        if resp.status_code != 422:
            print("FAIL: Duplicate serial number should be rejected (422).")
            sys.exit(1)

        print("Testing Accepted asset quantity exactly matches asset inputs")
        payload["lines"][1]["accepted_quantity"] = 3
        payload["lines"][1]["asset_details"] = [
            {"serial_no": "SN-X1-NEW", "model": "M1"},
            {"serial_no": "SN-X2-NEW", "model": "M2"}
        ]
        resp = await client.post("/api/receipts", json=payload, headers=headers_gsk)
        if resp.status_code != 422:
            print("FAIL: Mismatched asset quantity should be rejected (422).")
            sys.exit(1)

        print("All 18 tests logic PASSED.")

if __name__ == "__main__":
    asyncio.run(main())
