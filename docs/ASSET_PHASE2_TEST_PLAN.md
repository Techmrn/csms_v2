# Asset Phase 2 Test Plan

This document outlines the test plan for verifying Asset Phase 2 functionality.

## Prerequisites
- Apply migrations: `alembic upgrade head`
- Run the server: `python -m uvicorn app.main:app --port 8000`

## Test Cases

### 1. Asset Issue
- Create an Issue with an ASSET line.
- Provide `asset_ids` matching the `quantity`.
- Verify the individual Asset rows transition to `ASSIGNED`.
- Verify `IssueLineAsset` is created.
- Verify `AssetMovement` (type=ASSIGNMENT) is created.

### 2. Asset Transfer (Dispatch)
- Create a Transfer dispatching an ASSET line.
- Provide `asset_ids`.
- Verify individual Asset rows transition to `ASSIGNED` and their `current_store_id` is nullified.
- Verify `TransferLineAsset` is created.
- Verify `AssetMovement` (type=TRANSFER) is created.

### 3. Asset Transfer (Receive)
- Receive the transferred ASSET line.
- Verify individual Asset rows transition to `IN_STOCK` and their `current_store_id` becomes the destination store.
- Verify `AssetMovement` (type=RECEIPT) is created.
- Verify that attempting a short/excess receipt for ASSET lines raises an HTTP 422 error.

### 4. Asset Return
- Return an ASSET line referencing the exact `original_issue_line_id`.
- Provide `asset_ids`.
- Verify the Asset rows transition to `IN_STOCK` at the returning store.
- Verify `StockReturnLineAsset` is created.
- Verify `AssetMovement` (type=RETURN) is created.

### 5. Asset Lifecycle Management
- **Repair**: Send an IN_STOCK/ASSIGNED asset to repair. Verify it transitions to `UNDER_REPAIR` and `AssetRepair` is created.
- **Repair Return**: Return the repaired asset. Verify its status and location are restored from `AssetRepair`.
- **Unserviceable**: Mark an asset as `UNSERVICEABLE`.
- **Dispose**: Dispose an `UNSERVICEABLE` asset. Verify it transitions to `DISPOSED` and its location fields are nullified.
- **Lost**: Mark an asset as `LOST`. Verify its location fields are nullified.

## Expected Outcomes
All test cases must pass successfully with the correct state transitions, movement records, and authorization enforcement.
