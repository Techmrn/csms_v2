# Alembic Head Repair

The project had two Asset Phase 2 development heads. `0010_merge_asset_phase2_heads` joins them without changing business schema.

On an existing database currently at `f7f8467a4dae`, run `alembic upgrade head`. The idempotent `0009_asset_phase2_completion` will reconcile the Phase 2 objects, then the merge revision records a single head.

Do not use `alembic stamp` or manually edit `alembic_version`.
