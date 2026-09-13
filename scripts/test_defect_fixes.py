import asyncio
import httpx
from datetime import date

BASE_URL = "http://localhost:8000"

async def get_token(client, username):
    resp = await client.post("/api/auth/token", data={"username": username, "password": "DevOnly123!"})
    return resp.json()["access_token"]

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        token = await get_token(client, "dev_general_sk")
        headers = {"Authorization": f"Bearer {token}"}
        
        # We need an asset ID to test with.
        resp = await client.get("/api/assets", headers=headers, params={"store_id": 1, "status": "IN_STOCK"})
        assets = resp.json()
        if not assets:
            print("No assets found for testing")
            return
            
        asset_id = assets[0]["id"]
        item_id = assets[0]["item_id"]
        
        print(f"Testing duplicate issue for asset_id={asset_id}, item_id={item_id}")
        
        # The easiest way to test validation is at the service level or API level
        # To test issue, we need an indent. Let's just create one.
        # But wait, we can also test Transfer which requires a Requisition.
        # It's much easier to test the exception is thrown.
        
        # Let's create an indent
        indent_data = {
            "indent_date": str(date.today()),
            "financial_year_id": 1,
            "store_id": 1,
            "office_id": 1,
            "request_source": "PHYSICAL",
            "lines": [
                {
                    "item_id": item_id,
                    "requested_quantity": "2"
                }
            ]
        }
        
        resp = await client.post("/api/indents", headers=headers, json=indent_data)
        indent = resp.json()
        indent_id = indent["id"]
        
        # Forward to RECORDED -> VERIFIED -> APPROVED
        await client.post(f"/api/indents/{indent_id}/verify", headers=headers)
        await client.post(f"/api/indents/{indent_id}/approve", headers=headers)
        
        # Now try to finalize issue with duplicate asset ID
        issue_data = {
            "issue_date": str(date.today()),
            "lines": [
                {
                    "indent_line_id": indent["lines"][0]["id"],
                    "issued_quantity": "2",
                    "asset_ids": [asset_id, asset_id]
                }
            ]
        }
        
        resp = await client.post(f"/api/issues/finalize-indent/{indent_id}", headers=headers, json=issue_data)
        if resp.status_code == 422:
            print(f"PASS: Duplicate issue rejected with 422 - {resp.json()}")
        else:
            print(f"FAIL: Duplicate issue not rejected with 422! Status={resp.status_code}")
            print(resp.json())

if __name__ == "__main__":
    asyncio.run(main())
