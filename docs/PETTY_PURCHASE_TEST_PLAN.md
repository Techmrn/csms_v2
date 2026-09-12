# CSMS V2 — Petty Purchase Test Plan

Test against `AGENTS.md` and the current PostgreSQL database.

## Core

1. Storekeeper can create consumable petty purchase.
2. Asset item is rejected.
3. Purchase date outside FY is rejected.
4. Wrong store assignment is rejected.
5. Duplicate item lines are rejected.
6. Quantity must be positive.
7. Immediate issue quantity cannot exceed purchase quantity.
8. Temporary item creates a `TEMP-xxxxxx` consumable Item with `is_temporary=true`.

## Workflow

9. OPEN petty purchase requires controller verification before posting.
10. Central Store verification is restricted to Deputy Superintendent, Stock & Stores.
11. Branch verification is restricted to that Branch Head.
12. Wrong controlling officer is rejected.
13. Posting an OPEN purchase is rejected.
14. Reposting a POSTED purchase is rejected.

## Stock posting

15. Normal petty purchase creates exactly one `PETTY_PURCHASE` StockMovement per line with quantity_in = purchase quantity.
16. Current stock increases exactly by purchased quantity.
17. Stock Register contains the petty purchase movement.
18. Zero immediate issue leaves the full purchased quantity in stock.
19. Immediate issue creates one finalized Issue linked to the selected indent.
20. Immediate issue creates `ISSUE` StockMovement only for positive immediate-issue quantities.
21. Immediate issue lines with quantity 0 create no ISSUE movement.
22. The same posting_group_id is used for the petty purchase and immediate issue movements created in one posting.
23. Stock can be zero before purchase; immediate issue may consume the just-purchased quantity.
24. Immediate issue cannot exceed stock available after adding the petty purchase.

## Indent interaction

25. An indent is required when any immediate issue quantity is positive.
26. An indent is rejected if it belongs to another Store.
27. An indent that already has an Issue cannot be reused.
28. Immediate issue item must exist on the linked indent.
29. Immediate issue cannot exceed indent requested quantity.
30. Posting immediate issue finalizes the linked indent.
31. Issue Register contains the generated Issue.
32. The Issue reference_no identifies the petty purchase number.

## Ledger / integrity

33. No duplicate `PETTY_PURCHASE` StockMovement rows on repeated POST.
34. No zero-quantity StockMovement rows.
35. Ledger balance equals API current stock.
36. Transaction is atomic: if immediate Issue creation fails, the petty purchase StockMovement is also rolled back.
37. Concurrent POST of the same petty purchase produces only one successful posting.
38. Concurrent petty purchases against the same Store/FY/Item cannot create inconsistent negative stock after the immediate issue.
39. Cross-FY date validation is enforced.

## Important operational case

40. Create a temporary consumable through Petty Purchase, leave it in OPEN/VERIFIED state, then create a manual indent using the generated temporary Item. Post the petty purchase with immediate issue against that indent and verify both stock IN and issue OUT are correct.
