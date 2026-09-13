# CSMS V2 — Hardened Backend Baseline

This baseline is the implementation source of truth before UI work.

## Included

- Organization: Office / Section / Store
- Directorate + Central Store
- Central Press as separate Branch Office + Store
- User / Role / Permission / Store scope
- Financial Year
- Category: CONSUMABLE / ASSET
- Item / Unit / InventoryPolicy foundation
- Opening Stock
- Receipt
- Manual Indent + actual Issue quantity (0 / partial / full)
- Stock Return
- Central Store Requisition
- Branch Head approval
- Deputy Superintendent approval
- Central Store Transfer Out
- Branch Transfer In
- Transfer discrepancy workflow
- Petty Purchase, including temporary consumable items and immediate issue
- Stock Verification
- Adjustment
- Consumable Unserviceable
- Asset Receipt / Register
- Asset Issue mapping
- Asset Transfer mapping
- Asset Return mapping
- Asset Repair state/history
- Asset Unserviceable / Disposal / Lost
- JWT authentication
- RBAC + resource scope
- Async SQLAlchemy 2.x + PostgreSQL
- Row-level locking / idempotent posting protections

## Current migration head

`0009_asset_phase2_completion`

The 0009 migration creates or converges the Asset Phase 2 mapping/repair tables so
both a clean installation and a development database that already has those objects
can reach the same forward schema.

## Important final architecture

```text
JWT
  -> authenticated user
  -> permission
  -> resource scope
  -> workflow state
  -> business validation
  -> service
  -> posting / asset movement
  -> PostgreSQL
```

No client-supplied `actor_id` is part of the public request contract.
