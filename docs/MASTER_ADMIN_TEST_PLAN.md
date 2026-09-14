# CSMS V2 — Master & User Administration Test Plan

## Access

1. Unauthenticated `/app/admin` redirects to `/login`.
2. A user without `MASTER_DATA_MANAGE`, `ORGANIZATION_MANAGE`, or `USER_MANAGE` cannot enter Administration.
3. `dev_admin` can access Administration after `seed.py`, `seed_dev_users.py`, and `set_dev_passwords.py`.

## Master Data

4. Category create allows only `CONSUMABLE` and `ASSET`.
5. `MATERIAL` is not offered as a category type.
6. Category update cannot change type after it is used.
7. Unit create/update works and decimal flag is retained.
8. Item creation requires an active Category and Unit.
9. Item creation rejects duplicate Item code and duplicate name within a Category.
10. Item code is immutable after creation.
11. Item category/unit cannot be changed after relevant stock/asset history exists.
12. Financial Year rejects invalid dates and overlapping periods.
13. Only one Financial Year can be current.
14. Closed FY is visible and cannot be silently reopened through unrelated screens.
15. Inventory Policy is optional per Store + Consumable Item.
16. FIFO/LIFO/FEFO, reorder, low-stock, batch and expiry fields can be left blank.
17. Inventory Policy rejects Asset items.

## Organization

18. Office can be created and edited.
19. Office code is immutable.
20. Store can be created for a valid office.
21. CENTRAL store can only belong to a Directorate office.
22. BRANCH store can only belong to a Branch office.
23. More than one active CENTRAL store is rejected.
24. Section can be created only under a valid Office.
25. Section code is unique within an Office.

## Users

26. User can be created with an existing Role and zero or more assigned Stores.
27. User username and code are unique.
28. Section must belong to the selected Office.
29. User roles are selected from existing active roles only.
30. User stores are selected from active stores only.
31. Passwords are stored as Argon2 hashes.
32. Existing user can be edited.
33. Existing password remains unchanged when reset field is blank.
34. Supplied reset password replaces the existing hash.
35. User can be activated/deactivated, except an administrator cannot deactivate their own account.
36. Roles & Permissions page is read-only; arbitrary permission combinations cannot be created from the UI.

## Existing System Protection

37. `pytest tests/ -v` remains green.
38. No existing transaction schemas are changed by the master UI.
39. No actor_id is reintroduced.
40. No stock balance source-of-truth is added.
41. No transaction history is deleted by master updates.
