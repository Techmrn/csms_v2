# CSMS V2 — Central Store Requisition + Transfer Test Plan

Environment should be the local PostgreSQL `csms_v2` database.

Run `python scripts/seed_dev_users.py` first for development actor IDs. The users are development-only actors; the real authentication system will replace `actor_id` plumbing later.

## Roles used by the workflow

- `dev_press_sk` — Branch Storekeeper / Central Press Store
- `dev_press_head` — Branch Head / Central Press
- `dev_deputy` — Deputy Superintendent, Stock & Stores / Directorate
- `dev_general_sk` — General Storekeeper / Central Store
- `dev_assistant_sk` — Assistant Storekeeper / Central Store

## Required tests

### Requisition

1. Branch Storekeeper creates a consumable requisition from Central Press Store.
2. Central Store cannot be used as the requesting branch store.
3. Requesting store must belong to requesting office.
4. Asset item is rejected.
5. Date outside FY is rejected.
6. Duplicate item lines are rejected.
7. Non-assigned storekeeper cannot create the requisition.
8. Branch Head approves only their own office requisition.
9. Creator cannot self-approve.
10. Branch Head rejection moves requisition to REJECTED.
11. Deputy Superintendent approves only after Branch Head approval.
12. Central approval requires a decision for every line.
13. Approved quantity cannot exceed requested quantity.
14. Approval does not change stock.

### Dispatch

15. Only Central Store execution users can dispatch.
16. Non-Central Store users cannot dispatch.
17. Dispatch quantity cannot exceed approved quantity.
18. Dispatch quantity cannot exceed Central Store available stock.
19. Actual dispatch may be less than approval.
20. If all dispatch quantities are zero, requisition closes without creating a transfer or stock movement.
21. If Central Store has only 250 available for an approved 300, dispatch 250 and close after receipt; no automatic pending 50 is created.
22. Dispatch creates one Transfer and one TRANSFER_OUT movement for each positive line.
23. Central Store stock decreases by actual dispatched quantity.
24. Duplicate/concurrent dispatch of the same requisition is prevented.

### Receive

25. Only destination Branch Storekeeper can receive.
26. Full receipt creates TRANSFER_IN equal to dispatched quantity.
27. Full receipt closes transfer and requisition.
28. Short receipt posts only physically received quantity and creates discrepancy.
29. Excess physical receipt creates discrepancy; only dispatched quantity enters stock until resolved.
30. Unresolved discrepancy keeps transfer/requisition open.
31. Discrepancy resolution with ADDITIONAL_RECEIPT posts only the discrepancy quantity and then closes when all discrepancies are resolved.
32. Discrepancy resolution is restricted to authorized controlling officers of source/destination offices.

### Cross-FY

33. Dispatch on 31-Mar in FY A and receipt on 01-Apr in FY B is supported.
34. TRANSFER_OUT uses source FY.
35. TRANSFER_IN uses receiving FY.
36. Requisition remains linked across the two movements.

### Ledger

37. Reconcile source and destination store balances against raw ledger sums.
38. No negative Central Store stock.
39. No duplicate transfer line stock movements.
40. No zero-quantity StockMovement rows.
