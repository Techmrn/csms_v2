# CSMS V2 Asset Phase 1 Test Plan

Use the existing PostgreSQL database and the current final authenticated codebase.

Do not modify business rules to make tests pass.

## Asset acquisition through Receipt

1. Create a receipt containing one consumable line — existing behavior unchanged.
2. Create a receipt containing one asset line.
3. Verify asset receipt requires authentication.
4. Verify asset receipt requires existing receipt permission and store scope.
5. Verify an asset line with accepted quantity 2 requires exactly 2 asset detail entries.
6. Verify accepted quantity 2 with only 1 asset detail entry is rejected.
7. Verify accepted quantity 2 with 3 asset details is rejected.
8. Verify duplicate serial number is rejected when the serial already exists.
9. Verify two asset records receive distinct Asset Numbers.
10. Verify Asset status is `IN_STOCK` after posting.
11. Verify Asset current_store_id equals the Receipt store.
12. Verify Asset acquisition_financial_year_id equals the Receipt FY.
13. Verify an AssetMovement `RECEIPT` exists for each accepted asset.
14. Verify ReceiptLineAsset links each asset to the exact ReceiptLine.
15. Verify asset receipt creates NO consumable StockMovement.
16. Verify mixed receipt: consumable lines create StockMovement, asset lines create Assets.
17. Verify rejected asset quantity does not create Assets.
18. Verify pending inspection prevents receipt verification/posting as before.
19. Verify posted receipt cannot be posted twice.
20. Verify a failed mixed receipt post rolls back both consumable ledger movements and asset creation.

## Asset Register

21. Authenticated user can list assets.
22. Asset can be retrieved by ID.
23. Asset movement history can be retrieved.
24. Asset status/store/item filters work.
25. Historical asset remains visible after later status changes.

## Ledger reconciliation

26. Consumable stock remains exactly equal to ledger sum after mixed receipts.
27. Asset records do not affect the consumable ledger.
28. No duplicate Asset Numbers exist.
29. No duplicate non-null serial numbers exist.

## Security

30. Unauthenticated Asset Register request returns 401.
31. User without Asset view authority is rejected if `ASSET_VIEW` is enforced in the final authorization layer.
32. A user cannot use receipt Store scope to create assets in another Store.
