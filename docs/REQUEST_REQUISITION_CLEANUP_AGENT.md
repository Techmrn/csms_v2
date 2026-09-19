# CSMS V2 — Request / Requisition Cleanup Agent Instructions

Use the current project as the authoritative baseline. Do not merge `Indent` and `CentralStoreRequisition`. Keep the workflows separate.

## Already applied in this package
- Requested requisition quantity is shown as read-only on review pages.
- Central approval edits only `approved_quantity`; it does not overwrite `requested_quantity`.
- Requisition list is view-first; approval forms moved to the detail page.
- Requisition detail shows current availability from the configured fulfilling store for the existing Central Store workflow.
- API get endpoints for indents, requisitions and transfers now enforce view permission plus store scope.
- Petty purchase list API now receives `current_user` correctly.
- `STOCK_RETURN_CREATE` is now an explicit permission in the catalogue and assigned to `SECTION_USER`. Run the normal seed synchronizer after deployment so the database role-permission mapping is refreshed. Do not run Alembic.
- `My Activity` shows only records created by the logged-in user; it is not a substitute for the department-wide Transaction Register.
- Preserve the office→section dependent dropdown implementation already present.

## Mandatory business rules for the next agent pass
1. Indent and requisition remain separate.
2. Indent: request → approval → issue. Stock changes only at issue.
3. Requisition: inter-store request → approval → transfer dispatch → outward movement → destination receive.
4. Requested quantity is immutable after submission.
5. Approver may change only approved quantity.
6. Actual issue / dispatch / receive quantities are separate facts.
7. Approval availability must be calculated from the store that actually fulfils the request.
8. Posting must lock/recheck the current source-store stock; displayed availability is informational and does not reserve stock.
9. Branch-to-branch transfer must eventually support: source store, destination store, source-store availability, source-store dispatch, outward pass, destination receive, source OUT and destination IN.
10. Creator cannot approve the same document. Authorizer cannot post. Posted ledger transactions are immutable.
11. Every API GET/action must enforce permission and scope. UI hiding is never the security boundary.
12. Section User may create returns only for their own office/section and must see the Return to Store menu.
13. My Activity may expose only the current user’s own history.

## Important schema constraint for the next pass
The current database schema has no persistent `source_store_id` on `CentralStoreRequisition` and no `approved_quantity` on `IndentLine`. Do not fake either value in remarks or overwrite requested/issued quantities. A future authorized migration should add: `central_store_requisitions.source_store_id` and `indent_lines.approved_quantity`. Until that migration is explicitly authorized, do not claim full branch-to-branch requisition support or separate indent approval quantities are complete.

## No automatic migration
Do not run `alembic upgrade`, create/drop tables, or change the database schema during this phase.

## Validation
- `python -m compileall app scripts`
- run the RBAC/static tests
- verify SECTION_USER cannot open another office/section’s returns or indents
- verify approver cannot edit requested quantity
- verify central approval displays requested / available / approved separately
- verify storekeeper posting rechecks current source stock
