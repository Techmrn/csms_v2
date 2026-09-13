# CSMS V2 Hardened Baseline Verification

Use the current PostgreSQL development database. Do not reset production data.

1. `alembic heads` must show exactly one head: `0010_merge_asset_phase2_heads`.
2. `alembic current` must report that head after `alembic upgrade head`.
3. Authentication: unauthenticated business routes return 401.
4. Asset register list/detail/history enforce ASSET_VIEW and resource/store scope.
5. Asset Phase 2 tests use the current API routes.
6. Asset Issue/Transfer/Return mapping tables prevent duplicate asset IDs.
7. Repair restores the exact prior state/location.
8. Asset unserviceable/disposal/lost create AssetMovement and no consumable StockMovement.
9. Petty Purchase StockMovements and generated immediate Issue movements record the authenticated user.
10. Existing consumable ledger and transaction regressions remain unchanged.
