# UI Foundation Test Plan

## Test-only rule

Do not modify application code during this verification. Report defects only.

## Checks

1. `GET /login` returns 200.
2. Invalid login returns 401 and does not establish a session.
3. Valid seeded user login returns 303 to `/app` and sets HttpOnly `csms_access_token`.
4. `/app` without login redirects to `/login`.
5. `/app` with valid login returns 200.
6. Dashboard displays authenticated user's role.
7. Visible store selector contains only stores allowed by AuthorizationService.
8. Financial year selector lists configured financial years.
9. Branch Storekeeper cannot select/query Central Store through UI context.
10. Director can see department-wide stores.
11. `/app/stock` without login redirects to `/login`.
12. `/app/stock` with authorized store returns current ledger-derived balances.
13. `/app/assets` without login redirects to `/login`.
14. Asset page respects existing Asset visibility scope.
15. `/app/items` returns active Item master records.
16. Logout removes the browser authentication cookie and redirects to `/login`.
17. Existing `pytest tests/ -v` regression remains green.
18. No Alembic migration is added by this UI phase.
19. No business rule is implemented in templates or JavaScript.
