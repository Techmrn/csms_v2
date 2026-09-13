# Antigravity Agent Instructions — Asset Phase 1

Work on the user's CURRENT CSMS V2 repository, not an older archive.

Read:
- AGENTS.md
- docs/ASSET_PHASE1_INTEGRATION.md
- docs/ASSET_PHASE1_TEST_PLAN.md

Implement only Asset Phase 1:

1. Asset tables/models/migration `0008_assets`.
2. Asset Register and movement-history endpoints.
3. Integrate Assets into the EXISTING Receipt workflow.
4. Keep existing consumable Receipt behavior unchanged.
5. Allow mixed Receipt lines (consumable + asset).
6. For asset lines, accepted quantity must equal the count of individual asset detail entries.
7. Create one Asset + AssetDetail + AssetMovement(RECEIPT) + ReceiptLineAsset per accepted asset.
8. Do not create StockMovement for assets.
9. Use authenticated `current_user.id` only; do not add actor_id anywhere.
10. Preserve the existing final JWT/RBAC implementation.
11. Reuse the existing receipt permission and store-scope checks.
12. Do not modify Issue, Transfer, Return, Requisition, Petty Purchase, or Stock Control behavior yet.
13. Do not implement asset petty purchase.

Important state model:
- IN_STOCK
- ASSIGNED
- UNDER_REPAIR
- UNSERVICEABLE
- DISPOSED
- LOST

Phase 1 may only create IN_STOCK assets. Later lifecycle states are reserved for Phase 2.

Run the migration and execute every test in docs/ASSET_PHASE1_TEST_PLAN.md.

Do not change AGENTS.md business rules.

If an existing file has changed since the earlier authentication refactor, merge carefully; do not overwrite the user's current authentication/RBAC work.

Report:
- files changed
- migration status
- tests PASS/FAIL
- any business-rule conflict
- any existing regression caused by the integration

Stop on a business-rule contradiction rather than inventing a new rule.
