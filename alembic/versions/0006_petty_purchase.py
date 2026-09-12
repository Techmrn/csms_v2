"""add petty purchase workflow

Revision ID: 0006_petty_purchase
Revises: 0005_requisition_transfer
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_petty_purchase"
down_revision = "0005_requisition_transfer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS petty_purchase_no_seq START WITH 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS temp_item_no_seq START WITH 1")

    op.add_column("items", sa.Column("is_temporary", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "petty_purchases",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("petty_purchase_no", sa.String(50), nullable=False, unique=True),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("indent_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("invoice_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["indent_id"], ["indents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status in ('OPEN','VERIFIED','POSTED','CANCELLED')",
            name="ck_petty_purchases_status_valid",
        ),
    )
    op.create_index("ix_petty_purchases_store_status", "petty_purchases", ["store_id", "status"])
    op.create_index("ix_petty_purchases_fy_date", "petty_purchases", ["financial_year_id", "purchase_date"])
    op.create_index("ix_petty_purchases_indent", "petty_purchases", ["indent_id"])

    op.create_table(
        "petty_purchase_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("petty_purchase_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("temporary_item_name", sa.String(255), nullable=True),
        sa.Column("temporary_specification", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("immediate_issue_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["petty_purchase_id"], ["petty_purchases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("petty_purchase_id", "item_id", name="uq_petty_purchase_lines_purchase_item"),
        sa.CheckConstraint("quantity > 0", name="ck_petty_purchase_lines_quantity_positive"),
        sa.CheckConstraint(
            "immediate_issue_quantity >= 0 AND immediate_issue_quantity <= quantity",
            name="ck_petty_purchase_lines_immediate_issue_valid",
        ),
    )
    op.create_index("ix_petty_purchase_lines_item", "petty_purchase_lines", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_petty_purchase_lines_item", table_name="petty_purchase_lines")
    op.drop_table("petty_purchase_lines")
    op.drop_index("ix_petty_purchases_indent", table_name="petty_purchases")
    op.drop_index("ix_petty_purchases_fy_date", table_name="petty_purchases")
    op.drop_index("ix_petty_purchases_store_status", table_name="petty_purchases")
    op.drop_table("petty_purchases")
    op.drop_column("items", "is_temporary")
    op.execute("DROP SEQUENCE IF EXISTS temp_item_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS petty_purchase_no_seq")
