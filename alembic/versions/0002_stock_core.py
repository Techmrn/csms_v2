"""add opening stock and stock ledger core

Revision ID: 0002_stock_core
Revises: 0001_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_stock_core"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "financial_year_id", "item_id", name="uq_stock_accounts_store_fy_item"),
    )

    op.create_table(
        "stock_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_no", sa.String(100), nullable=True),
        sa.Column("manufacture_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("reference_type", sa.String(40), nullable=True),
        sa.Column("reference_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "store_id", "item_id", "financial_year_id", "batch_no",
            name="uq_stock_batches_store_item_fy_batch",
        ),
    )
    op.create_index("ix_stock_batches_item_expiry", "stock_batches", ["item_id", "expiry_date"])

    op.create_table(
        "opening_stocks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opening_no", sa.String(50), nullable=False, unique=True),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_opening_stocks_store_fy_status", "opening_stocks", ["store_id", "financial_year_id", "status"])

    op.create_table(
        "opening_stock_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opening_stock_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["opening_stock_id"], ["opening_stocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("opening_stock_id", "item_id", name="uq_opening_stock_lines_opening_item"),
        sa.CheckConstraint("quantity > 0", name="ck_opening_stock_lines_quantity_positive"),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("stock_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("movement_type", sa.String(30), nullable=False),
        sa.Column("quantity_in", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("quantity_out", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("reference_type", sa.String(40), nullable=False),
        sa.Column("reference_id", sa.BigInteger(), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["stock_batch_id"], ["stock_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("quantity_in >= 0", name="ck_stock_movements_quantity_in_nonnegative"),
        sa.CheckConstraint("quantity_out >= 0", name="ck_stock_movements_quantity_out_nonnegative"),
        sa.CheckConstraint(
            "((quantity_in > 0 AND quantity_out = 0) OR (quantity_out > 0 AND quantity_in = 0))",
            name="ck_stock_movements_exactly_one_direction",
        ),
        sa.UniqueConstraint(
            "reference_type", "reference_id", "item_id", "movement_type",
            name="uq_stock_movements_reference_item_type",
        ),
    )
    op.create_index(
        "ix_stock_movements_store_fy_item_date",
        "stock_movements",
        ["store_id", "financial_year_id", "item_id", "movement_date"],
    )
    op.create_index("ix_stock_movements_reference", "stock_movements", ["reference_type", "reference_id"])
    op.create_index("ix_stock_movements_posting_group", "stock_movements", ["posting_group_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_movements_posting_group", table_name="stock_movements")
    op.drop_index("ix_stock_movements_reference", table_name="stock_movements")
    op.drop_index("ix_stock_movements_store_fy_item_date", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("opening_stock_lines")
    op.drop_index("ix_opening_stocks_store_fy_status", table_name="opening_stocks")
    op.drop_table("opening_stocks")
    op.drop_index("ix_stock_batches_item_expiry", table_name="stock_batches")
    op.drop_table("stock_batches")
    op.drop_table("stock_accounts")
