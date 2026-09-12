"""add central store requisition and stock transfer workflows

Revision ID: 0005_requisition_transfer
Revises: 0004_receipts_returns
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_requisition_transfer"
down_revision = "0004_receipts_returns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS requisition_no_seq START WITH 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS transfer_no_seq START WITH 1")

    op.create_table(
        "central_store_requisitions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("requisition_no", sa.String(50), nullable=False, unique=True),
        sa.Column("requisition_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("requesting_office_id", sa.BigInteger(), nullable=False),
        sa.Column("requesting_store_id", sa.BigInteger(), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("branch_approved_by", sa.BigInteger(), nullable=True),
        sa.Column("branch_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("central_approved_by", sa.BigInteger(), nullable=True),
        sa.Column("central_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.BigInteger(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requesting_office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requesting_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_approved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["central_approved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status in ('SUBMITTED','BRANCH_APPROVED','CENTRAL_APPROVED','READY_FOR_TRANSFER','DISPATCHED','RECEIVED','DISCREPANCY','CLOSED','REJECTED','CANCELLED')",
            name="ck_csr_status_valid",
        ),
    )
    op.create_index("ix_csr_requesting_store_status", "central_store_requisitions", ["requesting_store_id", "status"])
    op.create_index("ix_csr_fy_date", "central_store_requisitions", ["financial_year_id", "requisition_date"])

    op.create_table(
        "central_store_requisition_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("requisition_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("dispatched_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["requisition_id"], ["central_store_requisitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("requisition_id", "item_id", name="uq_csr_lines_requisition_item"),
        sa.CheckConstraint("requested_quantity > 0", name="ck_csr_requested_quantity_positive"),
        sa.CheckConstraint("approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity)", name="ck_csr_approved_quantity_valid"),
        sa.CheckConstraint("dispatched_quantity >= 0", name="ck_csr_dispatched_nonnegative"),
        sa.CheckConstraint("received_quantity >= 0", name="ck_csr_received_nonnegative"),
        sa.CheckConstraint("dispatched_quantity <= coalesce(approved_quantity, 0)", name="ck_csr_dispatched_not_greater_approved"),
        sa.CheckConstraint("received_quantity <= dispatched_quantity", name="ck_csr_received_not_greater_dispatched"),
    )
    op.create_index("ix_csr_lines_item", "central_store_requisition_lines", ["item_id"])

    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("transfer_no", sa.String(50), nullable=False, unique=True),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("source_store_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_store_id", sa.BigInteger(), nullable=False),
        sa.Column("requisition_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("dispatched_by", sa.BigInteger(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_by", sa.BigInteger(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.BigInteger(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requisition_id"], ["central_store_requisitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dispatched_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("source_store_id <> destination_store_id", name="ck_transfer_source_destination_different"),
        sa.CheckConstraint("status in ('APPROVED','DISPATCHED','RECEIVED','DISCREPANCY','CLOSED','CANCELLED')", name="ck_transfer_status_valid"),
    )
    op.create_index("ix_transfers_requisition", "stock_transfers", ["requisition_id"])
    op.create_index("ix_transfers_source_status", "stock_transfers", ["source_store_id", "status"])
    op.create_index("ix_transfers_destination_status", "stock_transfers", ["destination_store_id", "status"])

    op.create_table(
        "stock_transfer_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("transfer_id", sa.BigInteger(), nullable=False),
        sa.Column("requisition_line_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["transfer_id"], ["stock_transfers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requisition_line_id"], ["central_store_requisition_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("quantity > 0", name="ck_transfer_line_quantity_positive"),
    )
    op.create_index("ix_transfer_lines_item", "stock_transfer_lines", ["item_id"])

    op.create_table(
        "transfer_discrepancies",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("transfer_id", sa.BigInteger(), nullable=False),
        sa.Column("transfer_line_id", sa.BigInteger(), nullable=False),
        sa.Column("receive_date", sa.Date(), nullable=False),
        sa.Column("discrepancy_type", sa.String(30), nullable=False),
        sa.Column("discrepancy_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("reported_by", sa.BigInteger(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transfer_id"], ["stock_transfers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transfer_line_id"], ["stock_transfer_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("discrepancy_type in ('SHORT_RECEIPT','EXCESS_RECEIPT','DAMAGED','WRONG_ITEM','OTHER')", name="ck_transfer_discrepancy_type_valid"),
        sa.CheckConstraint("discrepancy_quantity > 0", name="ck_transfer_discrepancy_quantity_positive"),
        sa.CheckConstraint("status in ('OPEN','UNDER_REVIEW','RESOLVED','CLOSED')", name="ck_transfer_discrepancy_status_valid"),
    )
    op.create_index("ix_transfer_discrepancies_transfer_status", "transfer_discrepancies", ["transfer_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_transfer_discrepancies_transfer_status", table_name="transfer_discrepancies")
    op.drop_table("transfer_discrepancies")
    op.drop_index("ix_transfer_lines_item", table_name="stock_transfer_lines")
    op.drop_table("stock_transfer_lines")
    op.drop_index("ix_transfers_destination_status", table_name="stock_transfers")
    op.drop_index("ix_transfers_source_status", table_name="stock_transfers")
    op.drop_index("ix_transfers_requisition", table_name="stock_transfers")
    op.drop_table("stock_transfers")
    op.drop_index("ix_csr_lines_item", table_name="central_store_requisition_lines")
    op.drop_table("central_store_requisition_lines")
    op.drop_index("ix_csr_fy_date", table_name="central_store_requisitions")
    op.drop_index("ix_csr_requesting_store_status", table_name="central_store_requisitions")
    op.drop_table("central_store_requisitions")
    op.execute("DROP SEQUENCE IF EXISTS transfer_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS requisition_no_seq")
