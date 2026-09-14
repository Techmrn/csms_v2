"""enforce one non-legacy opening-stock entry per store/FY/item

Revision ID: 0015_opening_stock_one_per_store_fy
Revises: 0014_petty_purchase_issue_destination
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_opening_stock_one_per_store_fy"
down_revision = "0014_petty_purchase_issue_destination"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A store may have multiple opening documents in a FY, but an item may be
    # opened only once. The existing database may contain historical duplicates.
    # They must not be deleted or merged because opening lines can already be
    # reflected in the stock ledger. We therefore grandfather duplicate rows
    # and enforce the rule for all new/non-legacy rows.
    op.add_column(
        "opening_stock_lines",
        sa.Column("store_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "opening_stock_lines",
        sa.Column("financial_year_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "opening_stock_lines",
        sa.Column("legacy_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE opening_stock_lines osl
        SET store_id = os.store_id,
            financial_year_id = os.financial_year_id
        FROM opening_stocks os
        WHERE os.id = osl.opening_stock_id
    """))

    unresolved = conn.execute(sa.text("""
        SELECT COUNT(*)
        FROM opening_stock_lines
        WHERE store_id IS NULL OR financial_year_id IS NULL
    """)).scalar_one()
    if unresolved:
        raise RuntimeError("Cannot backfill opening-stock store/financial-year for existing lines.")

    # Keep the earliest line for each store/FY/item as the canonical row; mark
    # later historical duplicates so their stock/audit history remains intact.
    conn.execute(sa.text("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY store_id, financial_year_id, item_id
                       ORDER BY id
                   ) AS rn
            FROM opening_stock_lines
        )
        UPDATE opening_stock_lines osl
        SET legacy_duplicate = TRUE
        FROM ranked r
        WHERE osl.id = r.id AND r.rn > 1
    """))

    op.alter_column("opening_stock_lines", "store_id", nullable=False)
    op.alter_column("opening_stock_lines", "financial_year_id", nullable=False)
    op.alter_column("opening_stock_lines", "legacy_duplicate", server_default=None)

    # Remove the old, overly restrictive one-document-per-store/FY rule.
    # It may not exist in every historical database, so use a guarded SQL DO block.
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_opening_stocks_store_fy'
            ) THEN
                ALTER TABLE opening_stocks DROP CONSTRAINT uq_opening_stocks_store_fy;
            END IF;
        END$$;
    """))

    op.create_foreign_key(
        "fk_opening_stock_lines_store",
        "opening_stock_lines",
        "stores",
        ["store_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_opening_stock_lines_financial_year",
        "opening_stock_lines",
        "financial_years",
        ["financial_year_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Unique among current/non-legacy rows. Historical duplicates remain visible
    # and auditable but cannot be recreated going forward.
    op.create_index(
        "uq_opening_stock_lines_store_fy_item_current",
        "opening_stock_lines",
        ["store_id", "financial_year_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("legacy_duplicate = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_opening_stock_lines_store_fy_item_current", table_name="opening_stock_lines")
    op.drop_constraint("fk_opening_stock_lines_financial_year", "opening_stock_lines", type_="foreignkey")
    op.drop_constraint("fk_opening_stock_lines_store", "opening_stock_lines", type_="foreignkey")
    op.create_unique_constraint(
        "uq_opening_stocks_store_fy",
        "opening_stocks",
        ["store_id", "financial_year_id"],
    )
    op.drop_column("opening_stock_lines", "legacy_duplicate")
    op.drop_column("opening_stock_lines", "financial_year_id")
    op.drop_column("opening_stock_lines", "store_id")
