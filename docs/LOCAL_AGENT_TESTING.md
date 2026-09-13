# CSMS V2 Local Agent Testing

Use this repository as the source of truth. The local agent is a TESTER unless explicitly authorized to make a defect fix.

## Setup

Run:

```text
alembic heads
alembic current
alembic upgrade head
python scripts/seed.py
python scripts/seed_dev_users.py
python scripts/set_dev_passwords.py
```

Expected migration head:
`0010_merge_asset_phase2_heads`

## Test order

1. `pytest tests/test_auth_integration.py -v`
2. `pytest tests/test_asset_phase1.py -v`
3. `pytest tests/test_asset_phase2.py -v`
4. Existing transaction/regression scripts and module test plans.

Do not let the agent redesign APIs or create new schema fields.
