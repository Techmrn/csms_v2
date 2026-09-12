# CSMS V2 — Stock Verification / Adjustment / Unserviceable Test Plan

Use the existing PostgreSQL `csms_v2` database and test against `AGENTS.md`.

## A. Stock Verification
1. Assigned Central Storekeeper can create a verification for Central Store.
2. Assigned Branch Storekeeper can create a verification for its branch Store.
3. Unassigned store user cannot create a verification for another store.
4. Asset item is rejected.
5. Date outside FY is rejected.
6. Duplicate item lines are rejected.
7. System quantity is captured from the current authoritative StockMovement balance.
8. Physical quantity may be zero.
9. Verification starts in COUNTED state.
10. Controller can authorize Central Store verification only as Deputy Superintendent.
11. Branch Head can authorize only its own branch verification.
12. Creator cannot authorize the same verification.
13. Verification with zero variance closes on authorization.
14. Verification with variance becomes AUTHORIZED and does not change stock.
15. Authorization rejects if stock changed after the verification snapshot.

## B. Adjustment
16. Adjustment cannot be created before verification authorization.
17. Adjustment is consumable-only.
18. Positive variance creates ADJUSTMENT_IN.
19. Negative variance creates ADJUSTMENT_OUT.
20. Mixed verification can create one adjustment per direction.
21. Duplicate adjustment of the same direction for one verification is rejected.
22. Wrong-store actor cannot create/post adjustment.
23. Only the store controller can authorize adjustment.
24. Adjustment creator cannot authorize it.
25. Storekeeper can post only an authorized adjustment for their assigned store.
26. Authorizer cannot post the same adjustment.
27. ADJUSTMENT_IN creates one correct StockMovement per line.
28. ADJUSTMENT_OUT creates one correct StockMovement per line.
29. Adjustment OUT cannot exceed current stock.
30. Adjustment posting is rejected if stock changed after verification.
31. Reposting an adjustment is rejected.
32. Verification closes only after all required direction adjustments are posted.
33. Ledger reconciles after adjustments.

## C. Unserviceable
34. Assigned Storekeeper can report consumable unserviceable stock.
35. Asset item is rejected.
36. Date outside FY is rejected.
37. Duplicate item lines are rejected.
38. Controller verification is required before authorization.
39. Reporter cannot verify/authorize the same record.
40. Branch Head controls branch-store unserviceable records.
41. Deputy Superintendent controls Central Store unserviceable records.
42. Storekeeper cannot authorize unserviceable stock.
43. Storekeeper can post authorized unserviceable stock only for their assigned store.
44. Authorizer cannot post the same record.
45. Insufficient stock blocks posting.
46. Posting creates one `UNSERVICEABLE` OUT movement per positive line.
47. Zero stock movement rows are never created.
48. Reposting is rejected.
49. Ledger reconciles after unserviceable posting.
50. Closed FY cannot accept these transactions.

## D. Concurrency
51. Concurrent authorization of the same verification produces one valid result.
52. Concurrent creation of the same adjustment direction is prevented.
53. Concurrent posting of the same adjustment is idempotent.
54. Concurrent unserviceable posting cannot create negative stock.
