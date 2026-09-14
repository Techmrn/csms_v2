# Master & User Administration

The Administration area is intended for controlled setup and maintenance before daily transactions begin.

Routes:
- `/app/admin`
- `/app/admin/masters`
- `/app/admin/offices`
- `/app/admin/stores`
- `/app/admin/sections`
- `/app/admin/categories`
- `/app/admin/units`
- `/app/admin/items`
- `/app/admin/financial-years`
- `/app/admin/policies`
- `/app/admin/users`
- `/app/admin/roles`

The default development administrator is `dev_admin`.

Use `python scripts\seed.py`, `python scripts\seed_dev_users.py`, then `set CSMS_DEV_PASSWORD=...` and `python scripts\set_dev_passwords.py` for local development credentials.
