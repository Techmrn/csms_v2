# CSMS V2 — Manual Indent and Opening Stock Test Plan

## Manual Indent

1. Storekeeper can open Manual Indent for an assigned Store only.
2. Form contains:
   - Item
   - Unit
   - Requested Quantity
   - Available
   - Issued
   - Remarks
3. Unit is always the Item master unit.
4. Available is calculated from the authoritative ledger for consumables.
5. Available for assets is the count of IN_STOCK assets in the selected Store.
6. Issued defaults to zero and can be zero, partial, or full.
7. Issued > Requested is rejected.
8. Issued > Available is rejected for consumables.
9. Asset issues require exact Asset IDs and the count must equal Issued.
10. The same Asset ID cannot appear twice in a manual indent transaction.
11. Saving the manual indent creates:
    - the Indent
    - the Issue
    - all applicable StockMovement/AssetMovement rows
    in one atomic transaction.
12. No draft state is created.
13. No second "Finalize Issue" action is required.
14. Successful manual indent ends in FINALIZED.
15. Successful Issue ends in FINALIZED.
16. Zero-issued lines do not create ISSUE StockMovement.
17. Partial issue creates the exact quantity OUT.
18. Stock Register and Current Stock reconcile after save.

## Opening Stock

1. Assigned Central Storekeeper can enter opening stock for Central Store.
2. Assigned Branch Storekeeper can enter opening stock for its branch Store.
3. No controller authorization is required.
4. Consumable line creates one OPENING StockMovement.
5. Asset line creates individual Asset records.
6. Asset line creates AssetMovement OPENING for each physical asset.
7. Existing asset numbers are preserved.
8. Duplicate asset number in the same request is rejected.
9. Existing asset number already in the database is rejected.
10. Duplicate serial number in the same request is rejected.
11. Existing serial number already in the database is rejected.
12. Asset quantity must equal the number of asset records supplied.
13. Asset quantity must be a whole number.
14. Consumable lines cannot contain asset details.
15. Asset opening does not create consumable StockMovement.
16. Consumable opening does not create Asset records.
17. Save & Post is atomic; a failure rolls back both consumable and asset entries.
18. Posted opening is immutable through normal UI.
19. Opening posting is limited to the authenticated Storekeeper assigned to the Store.
20. Closed FY is rejected.
21. Date outside FY is rejected.
22. Current stock reconciles with OPENING + later stock movements.
23. Asset Register shows manually opened assets as IN_STOCK at the Store.

## UI row behavior

All multi-line entry screens start with exactly one empty row. The user clicks **+ Add row** to add additional lines. Empty unused rows are never required.
