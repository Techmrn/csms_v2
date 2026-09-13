import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000"

async def get_token(client, username):
    resp = await client.post("/api/auth/token", data={"username": username, "password": "DevOnly123!"})
    if resp.status_code != 200:
        print(f"Failed to get token for {username}: {resp.text}")
        sys.exit(1)
    return resp.json()["access_token"]

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        token_press_sk = await get_token(client, "dev_press_sk")
        token_general_sk = await get_token(client, "dev_general_sk")
        token_press_head = await get_token(client, "dev_press_head")
        token_deputy = await get_token(client, "dev_deputy")
        token_director = await get_token(client, "dev_director")
        
        headers_press_sk = {"Authorization": f"Bearer {token_press_sk}"}
        headers_general_sk = {"Authorization": f"Bearer {token_general_sk}"}
        headers_press_head = {"Authorization": f"Bearer {token_press_head}"}
        headers_deputy = {"Authorization": f"Bearer {token_deputy}"}
        headers_director = {"Authorization": f"Bearer {token_director}"}
        
        # PRESS-STORE is 2, CENTRAL is 1 based on dev seed data
        # Let's verify by just testing it
        STORE_CENTRAL = 1
        STORE_PRESS = 2
        
        tests = [
            ("A. dev_press_sk + store_id=PRESS-STORE", headers_press_sk, f"/api/assets?store_id={STORE_PRESS}", 200),
            ("B. dev_press_sk + store_id=CENTRAL", headers_press_sk, f"/api/assets?store_id={STORE_CENTRAL}", 403),
            ("C. dev_general_sk + store_id=CENTRAL", headers_general_sk, f"/api/assets?store_id={STORE_CENTRAL}", 200),
            ("D. dev_general_sk + store_id=PRESS-STORE", headers_general_sk, f"/api/assets?store_id={STORE_PRESS}", 403),
            ("E. dev_press_head + store_id=PRESS-STORE", headers_press_head, f"/api/assets?store_id={STORE_PRESS}", 200),
            ("F. dev_deputy + store_id=CENTRAL", headers_deputy, f"/api/assets?store_id={STORE_CENTRAL}", 200),
            ("G. dev_director + store_id=CENTRAL", headers_director, f"/api/assets?store_id={STORE_CENTRAL}", 200),
            ("G. dev_director + store_id=PRESS-STORE", headers_director, f"/api/assets?store_id={STORE_PRESS}", 200),
            ("H. No Authorization header", {}, "/api/assets", 401),
            ("I. Invalid JWT", {"Authorization": "Bearer invalid_token_here"}, "/api/assets", 401),
            ("J. dev_press_sk without store_id", headers_press_sk, "/api/assets", 200),
            ("K. dev_director without store_id", headers_director, "/api/assets", 200)
        ]
        
        all_passed = True
        print(f"{'Test Case':<45} | {'Expected':<8} | {'Actual':<8} | {'Result':<6}")
        print("-" * 75)
        for name, headers, url, expected in tests:
            resp = await client.get(url, headers=headers)
            passed = resp.status_code == expected
            if not passed:
                all_passed = False
            result_str = "PASS" if passed else "FAIL"
            print(f"{name[:43]:<45} | {expected:<8} | {resp.status_code:<8} | {result_str:<6}")
            if not passed:
                print(f"   -> Failed response: {resp.text}")

        if not all_passed:
            sys.exit(1)

        print("\nAll tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
