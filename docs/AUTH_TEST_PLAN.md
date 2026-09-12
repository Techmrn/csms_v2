# CSMS V2 — Authentication & RBAC Test Plan

Use the local PostgreSQL `csms_v2` database and the development users.

1. Valid login returns a bearer token.
2. Invalid password returns HTTP 401.
3. Unknown username returns HTTP 401.
4. Inactive user cannot log in.
5. Token can call `/api/auth/me`.
6. Invalid/expired token is rejected.
7. `/api/auth/me` exposes active roles, permissions, and assigned stores.
8. Central Storekeeper has Central Store permissions only.
9. Assistant Storekeeper has Central Store permissions only.
10. Deputy Superintendent has Central approval/verification permissions.
11. Branch Head has branch approval/verification permissions.
12. Branch Storekeeper has branch execution permissions.
13. System Admin permissions do not automatically imply business-store scope.
14. Role/permission data is loaded without AsyncSession lazy-loading/MissingGreenlet errors.
15. Passwords are stored as Argon2 hashes, never plaintext.
