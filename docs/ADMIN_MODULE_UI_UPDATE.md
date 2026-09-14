# CSMS V2 — Administration UI Update

## Changes

- System Administrator now lands directly on the Administration dashboard.
- The admin sidebar contains only administration actions plus **All Views**.
- API Documentation is hidden from the System Administrator sidebar.
- Administration dashboard redesigned with color-coded KPI cards, active/inactive status information and quick-create actions for Office, Store, Section and User.
- Organization has a dedicated page for Offices, Stores and Sections.
- All Views provides read-only access to operational registers across the department.
- Read-only administrator views were added for Requisitions, Transfers and Stock Control.
- System Administrator gets department-wide read visibility without gaining transaction-posting or approval permissions.
- Transaction buttons such as New/Verify/Post/Opening Entry are hidden from the System Administrator UI.
- The `Items` dashboard count no longer renders the Python dictionary `.items` method.
- Added a CSMS favicon.
- The `0013_master_user_admin_permissions` migration now widens `alembic_version.version_num` before Alembic records the long revision ID, preventing the PostgreSQL `VARCHAR(32)` failure on clean databases.

## Deployment after updating the ZIP

No new migration is required for this UI-only/admin-permission cleanup beyond the already-existing `0013` revision. On an existing development database, run:

```cmd
python scripts\seed.py
python scripts\set_dev_passwords.py
```

Then start the application:

```cmd
uvicorn app.main:app --reload
```
