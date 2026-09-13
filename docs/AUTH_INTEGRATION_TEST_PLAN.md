# CSMS V2 — Authentication Integration Test Plan

1. All non-auth application endpoints reject unauthenticated requests.
2. Valid JWTs are accepted.
3. Client actor_id values cannot impersonate another user.
4. Existing transaction business tests pass with bearer tokens.
5. Receipt create/verify/post enforce permission and store assignment.
6. Return create/verify/post enforce permission and store assignment.
7. Opening stock creation requires assigned-store authority and posting requires the store controller.
8. Central/branch role and store-scope rules remain unchanged.
9. No MissingGreenlet errors occur while loading authenticated roles/permissions/stores.
10. Previous module test suites remain green with authentication enabled.
