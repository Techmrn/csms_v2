import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000"

async def get_token(client, username):
    resp = await client.post("/api/auth/token", data={"username": username, "password": "DevOnly123!"})
    return resp.json()["access_token"]

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # We need an indent and an asset to issue. 
        # But this takes a lot of setup...
        pass

if __name__ == "__main__":
    asyncio.run(main())
