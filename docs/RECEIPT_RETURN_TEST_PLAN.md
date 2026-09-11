# CSMS V2 Receipt + Return Test Plan

Use the existing PostgreSQL `csms_v2` database and current `AGENTS.md` as the specification.

## Receipt

1. Create a consumable receipt with one line and `received_quantity=100`, `accepted_quantity=100`, `rejected_quantity=0`.
2. Verify the receipt.
3. Post the receipt.
4. Confirm one `RECEIPT` StockMovement with `quantity_in=100`.
5. Confirm current stock increases by 100.
6. Confirm Stock Register contains the receipt movement.
7. Create a receipt with `received=100`, `accepted=80`, `rejected=20`; post and confirm only +80 enters stock.
8. Create a receipt with `received=100`, `accepted=80`, `rejected=0`; verify must reject because 20 is pending inspection.
9. Verify `accepted + rejected > received` is rejected.
10. Verify duplicate items in the same receipt are rejected.
11. Verify asset items are rejected by this consumable receipt module.
12. Verify receipt date outside FY is rejected.
13. Verify posting an OPEN receipt is rejected until VERIFIED.
14. Verify posting the same receipt twice is rejected and does not duplicate StockMovement.
15. Verify a receipt with all quantities rejected can be verified and posted with no stock movement.

## Return

1. Use an existing finalized Issue of a consumable item.
2. Create a return to the original issuing Store.
3. Verify the return.
4. Post the return.
5. Confirm one `RETURN` StockMovement with `quantity_in` equal to the returned quantity.
6. Confirm current stock increases correctly.
7. Confirm the return references the exact original IssueLine.
8. Attempt return greater than the original issued quantity; it must reject.
9. Post two concurrent returns that together exceed the originally issued quantity; only an allowable total may succeed.
10. Verify returning Store different from the original issuing Store is rejected.
11. Verify returning Office/Section inconsistent with the original Issue destination is rejected.
12. Verify a non-finalized Issue cannot be returned.
13. Verify duplicate original IssueLine within the same return is rejected.
14. Verify posting the same return twice is rejected and does not duplicate StockMovement.
15. Verify a valid return can occur in a later open financial year than the original Issue.
16. Verify cross-year return creates its StockMovement in the return's FY while still referencing the original Issue.

## Ledger reconciliation

After tests, for every affected Store/FY/Item:

`Current Stock = SUM(quantity_in) - SUM(quantity_out)`

There must be no StockMovement with a zero quantity direction, and no duplicate movement created by repeated POST requests.
