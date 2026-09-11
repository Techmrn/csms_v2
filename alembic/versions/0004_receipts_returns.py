"""add receipts and stock returns

Revision ID: 0004_receipts_returns
Revises: 0003_indent_issue
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_receipts_returns"
down_revision = "0003_indent_issue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS receipt_no_seq START WITH 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS return_no_seq START WITH 1")

    op.create_table(
        "receipts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("receipt_no", sa.String(50), nullable=False, unique=True),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("supplier_name", sa.String(255), nullable=True),
        sa.Column("purchase_reference", sa.String(100), nullable=True),
        sa.Column("invoice_reference", sa.String(100), nullable=True),
        sa.Column("challan_reference", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_receipts_store_status", "receipts", ["store_id", "status"])
    op.create_index("ix_receipts_fy_date", "receipts", ["financial_year_id", "receipt_date"])

    op.create_table(
        "receipt_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("rejected_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("received_quantity > 0", name="ck_receipt_lines_received_quantity_positive"),
        sa.CheckConstraint("accepted_quantity >= 0", name="ck_receipt_lines_accepted_quantity_nonnegative"),
        sa.CheckConstraint("rejected_quantity >= 0", name="ck_receipt_lines_rejected_quantity_nonnegative"),
        sa.CheckConstraint(
            "accepted_quantity + rejected_quantity <= received_quantity",
            name="ck_receipt_lines_accepted_rejected_not_greater_than_received",
        ),
    )
    op.create_index("ix_receipt_lines_item", "receipt_lines", ["item_id"])

    op.create_table(
        "stock_returns",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("return_no", sa.String(50), nullable=False, unique=True),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("original_issue_id", sa.BigInteger(), nullable=False),
        sa.Column("returning_office_id", sa.BigInteger(), nullable=True),
        sa.Column("returning_section_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_issue_id"], ["issues.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["returning_office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["returning_section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_stock_returns_store_status", "stock_returns", ["store_id", "status"])
    op.create_index("ix_stock_returns_issue", "stock_returns", ["original_issue_id"])
    op.create_index("ix_stock_returns_fy_date", "stock_returns", ["financial_year_id", "return_date"])

    op.create_table(
        "stock_return_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("return_id", sa.BigInteger(), nullable=False),
        sa.Column("original_issue_line_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["return_id"], ["stock_returns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["original_issue_line_id"], ["issue_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("return_id", "original_issue_line_id", name="uq_stock_return_lines_return_issue_line"),
        sa.CheckConstraint("quantity > 0", name="ck_stock_return_lines_quantity_positive"),
    )
    op.create_index("ix_stock_return_lines_issue_line", "stock_return_lines", ["original_issue_line_id"])
    op.create_index("ix_stock_return_lines_item", "stock_return_lines", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_return_lines_item", table_name="stock_return_lines")
    op.drop_index("ix_stock_return_lines_issue_line", table_name="stock_return_lines")
    op.drop_table("stock_return_lines")
    op.drop_index("ix_stock_returns_fy_date", table_name="stock_returns")
    op.drop_index("ix_stock_returns_issue", table_name="stock_returns")
    op.drop_index("ix_stock_returns_store_status", table_name="stock_returns")
    op.drop_table("stock_returns")
    op.drop_index("ix_receipt_lines_item", table_name="receipt_lines")
    op.drop_table("receipt_lines")
    op.drop_index("ix_receipts_fy_date", table_name="receipts")
    op.drop_index("ix_receipts_store_status", table_name="receipts")
    op.drop_table("receipts")
    op.execute("DROP SEQUENCE IF EXISTS return_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS receipt_no_seq")
