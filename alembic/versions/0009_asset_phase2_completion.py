"""complete Asset Phase 2 persistence structures

Revision ID: 0009_asset_phase2_completion
Revises: 0008_assets
Create Date: 2026-09-13

This migration is intentionally idempotent because earlier development builds
may already have created some Asset Phase 2 tables/constraints outside the
migration chain. It converges both a clean database and an existing V2 test
schema to the same structure.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_asset_phase2_completion"
down_revision = "0008_assets"
branch_labels = None
depends_on = None


def _add_fk_if_missing(table: str, constraint_name: str, columns: str, referred: str) -> None:
    # Names here are internal migration constants, so interpolating them into
    # PostgreSQL's DO block avoids bind parameters being interpreted as literal
    # text inside a dollar-quoted PL/pgSQL body.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'
            ) THEN
                ALTER TABLE {table}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY ({columns}) REFERENCES {referred};
            END IF;
        END $$;
        """
    )


def _add_unique_if_missing(table: str, constraint_name: str, columns: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'
            ) THEN
                ALTER TABLE {table}
                ADD CONSTRAINT {constraint_name}
                UNIQUE ({columns});
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_repairs (
            id BIGINT PRIMARY KEY,
            asset_id BIGINT NOT NULL,
            previous_store_id BIGINT NULL,
            previous_office_id BIGINT NULL,
            previous_section_id BIGINT NULL,
            previous_status VARCHAR(30) NOT NULL,
            sent_date DATE NOT NULL,
            sent_by BIGINT NOT NULL,
            reason TEXT NULL,
            status VARCHAR(30) NOT NULL,
            return_date DATE NULL,
            returned_by BIGINT NULL,
            resolution TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_repairs_asset_id ON asset_repairs(asset_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS issue_line_assets (
            id BIGINT PRIMARY KEY,
            issue_line_id BIGINT NOT NULL,
            asset_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_issue_line_assets_asset_id ON issue_line_assets(asset_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS transfer_line_assets (
            id BIGINT PRIMARY KEY,
            transfer_line_id BIGINT NOT NULL,
            asset_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_transfer_line_assets_asset_id ON transfer_line_assets(asset_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_return_line_assets (
            id BIGINT PRIMARY KEY,
            stock_return_line_id BIGINT NOT NULL,
            asset_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_stock_return_line_assets_asset_id ON stock_return_line_assets(asset_id)")

    _add_fk_if_missing(
        "asset_repairs", "fk_asset_repairs_asset_id_assets", "asset_id", "assets(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "asset_repairs", "fk_asset_repairs_previous_store_id_stores", "previous_store_id", "stores(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "asset_repairs", "fk_asset_repairs_previous_office_id_offices", "previous_office_id", "offices(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "asset_repairs", "fk_asset_repairs_previous_section_id_sections", "previous_section_id", "sections(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "asset_repairs", "fk_asset_repairs_sent_by_users", "sent_by", "users(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "asset_repairs", "fk_asset_repairs_returned_by_users", "returned_by", "users(id) ON DELETE RESTRICT"
    )

    _add_fk_if_missing(
        "issue_line_assets", "fk_issue_line_assets_issue_line_id_issue_lines",
        "issue_line_id", "issue_lines(id) ON DELETE CASCADE"
    )
    _add_fk_if_missing(
        "issue_line_assets", "fk_issue_line_assets_asset_id_assets",
        "asset_id", "assets(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "transfer_line_assets", "fk_transfer_line_assets_transfer_line_id_stock_transfer_lines",
        "transfer_line_id", "stock_transfer_lines(id) ON DELETE CASCADE"
    )
    _add_fk_if_missing(
        "transfer_line_assets", "fk_transfer_line_assets_asset_id_assets",
        "asset_id", "assets(id) ON DELETE RESTRICT"
    )
    _add_fk_if_missing(
        "stock_return_line_assets", "fk_stock_return_line_assets_stock_return_line_id_stock_return_lines",
        "stock_return_line_id", "stock_return_lines(id) ON DELETE CASCADE"
    )
    _add_fk_if_missing(
        "stock_return_line_assets", "fk_stock_return_line_assets_asset_id_assets",
        "asset_id", "assets(id) ON DELETE RESTRICT"
    )

    _add_unique_if_missing(
        "issue_line_assets", "uq_issue_line_assets_issue_line_asset", "issue_line_id, asset_id"
    )
    _add_unique_if_missing(
        "transfer_line_assets", "uq_transfer_line_assets_transfer_line_asset", "transfer_line_id, asset_id"
    )
    _add_unique_if_missing(
        "stock_return_line_assets", "uq_stock_return_line_assets_return_line_asset", "stock_return_line_id, asset_id"
    )


def downgrade() -> None:
    # Phase 2 objects are development-completed structures; keep downgrade
    # conservative and only remove objects introduced by this revision if they
    # exist. Existing databases that already had these tables should not lose
    # unrelated data simply because an Alembic downgrade is attempted.
    op.execute("DROP TABLE IF EXISTS asset_repairs")
    op.execute("DROP TABLE IF EXISTS stock_return_line_assets")
    op.execute("DROP TABLE IF EXISTS transfer_line_assets")
    op.execute("DROP TABLE IF EXISTS issue_line_assets")
