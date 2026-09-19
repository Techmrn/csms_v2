# CSMS V2 — Corrected Phase Package

Baseline: the latest `application.zip` supplied by the user.

## Included corrections

1. **Indent and Requisition remain separate.** No database merge was introduced.
2. **Requisition approval UI is view-first.** The list no longer exposes inline approval editors. Approval is performed from the detail page.
3. **Requested quantity stays read-only.** For the existing requisition workflow, the approver edits only `approved_quantity`.
4. **Source-store availability is visible** on the requisition detail page for the current Central Store workflow.
5. **API GET scope hardening** was added to individual Indent, Requisition and Transfer reads.
6. **Petty Purchase API list bug fixed:** `current_user` was missing from the endpoint signature.
7. **Section User return creation permission is now explicitly catalogued** as `STOCK_RETURN_CREATE`, matching the role matrix.
8. **My Activity** was added. It shows only documents created by the logged-in user and does not replace the department-wide register.
9. Existing **office → section filtering** was preserved.
10. No Alembic upgrade was run and no database migration was applied.

## Deliberately not claimed as complete

The current database schema does not yet persist:

- a separate `source_store_id` on `CentralStoreRequisition`; and
- a separate `approved_quantity` on `IndentLine`.

Therefore this package does **not** pretend to provide complete branch-to-branch requisition support or separate approved-vs-requested quantities for online Indents. Those require an explicitly authorized schema migration. The included agent instructions describe the exact next step without modifying the database in this package.

## Validation performed

- Python compilation of `app`, `scripts`, and `tests`: PASS.
- New request/requisition cleanup static tests: 4/4 PASS.
- Python AST parsing of modified route/service files: PASS.
- Full application import could not be completed in this container because `asyncpg` is not installed in the execution environment. This is an environment limitation; no dependency installation was performed.
