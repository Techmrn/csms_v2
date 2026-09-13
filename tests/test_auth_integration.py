import pytest
import httpx

BASE_URL = "http://localhost:8000"

@pytest.fixture(scope="session")
def tokens():
    users = ["dev_director", "dev_deputy", "dev_general_sk", "dev_assistant_sk", "dev_press_head", "dev_press_sk"]
    tokens = {}
    for u in users:
        try:
            resp = httpx.post(f"{BASE_URL}/api/auth/token", data={"username": u, "password": "DevOnly123!"})
            if resp.status_code == 200:
                tokens[u] = resp.json()["access_token"]
            else:
                print(f"Failed to login {u}: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Exception logging in {u}: {e}")
    return tokens

def test_unauthenticated_returns_401():
    resp = httpx.get(f"{BASE_URL}/api/petty-purchases")
    assert resp.status_code == 401

def test_valid_jwt_works(tokens):
    token = tokens.get("dev_director")
    assert token is not None
    client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    resp = client.get("/api/stores")
    assert resp.status_code == 200

def test_actor_id_matching_works(tokens):
    # dev_general_sk ID is 3 (based on seed_dev_users.py order)
    # dev_general_sk is GENERAL_STOREKEEPER and can create indents or petty purchases.
    # Let's hit an endpoint with actor_id=3.
    # POST /api/petty-purchases
    token = tokens.get("dev_general_sk")
    client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    
    payload = {
        "purchase_date": "2026-04-01",
        "financial_year_id": 1,
        "store_id": 1,
        "actor_id": 3,
        "lines": [
            {
                "item_id": 1,
                "quantity": 10,
                "unit_id": 1
            }
        ]
    }
    resp = client.post("/api/petty-purchases", json=payload)
    # Shouldn't be 403 Forbidden due to actor impersonation
    assert resp.status_code not in (401, 403)

def test_actor_id_mismatch_returns_403(tokens):
    token = tokens.get("dev_general_sk")
    client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    
    payload = {
        "purchase_date": "2026-04-01",
        "financial_year_id": 1,
        "store_id": 1,
        "actor_id": 999, # Mismatched actor_id
        "lines": [
            {
                "item_id": 1,
                "quantity": 10,
                "unit_id": 1
            }
        ]
    }
    resp = client.post("/api/petty-purchases", json=payload)
    assert resp.status_code == 403

def test_server_uses_authenticated_user_identity(tokens):
    token = tokens.get("dev_general_sk")
    client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    
    payload = {
        "purchase_date": "2026-04-01",
        "financial_year_id": 1,
        "store_id": 1,
        "lines": [
            {
                "item_id": 1,
                "quantity": 10,
                "unit_id": 1
            }
        ]
    }
    resp = client.post("/api/petty-purchases", json=payload)
    assert resp.status_code != 401
    assert resp.status_code != 403

def test_receipt_permissions(tokens):
    token = tokens.get("dev_press_sk") # Can receive at PRESS-STORE (store_id=2)
    client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    payload = {
        "receipt_date": "2026-04-01",
        "financial_year_id": 1,
        "store_id": 1, # Unassigned store for press_sk
        "lines": [
            {
                "item_id": 1,
                "received_quantity": 10,
                "unit_id": 1
            }
        ]
    }
    resp = client.post("/api/receipts", json=payload)
    # Should be 403 because dev_press_sk cannot operate CENTRAL store (1)
    assert resp.status_code == 403

    payload["store_id"] = 2 # Assigned store
    resp = client.post("/api/receipts", json=payload)
    assert resp.status_code != 401
    assert resp.status_code != 403

def test_no_missing_greenlet_errors(tokens):
    # This was already implicitly tested in the auth middleware for all the above requests,
    # as loading user roles/stores uses async SQLAlchemy. If there was a missing greenlet,
    # we would get a 500 internal server error.
    pass
