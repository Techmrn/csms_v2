"""add stock verification, adjustments and unserviceable workflows

Revision ID: 0007_stock_control
Revises: 0006_petty_purchase
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_stock_control"
down_revision = "0006_petty_purchase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS stock_verification_no_seq START WITH 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS adjustment_no_seq START WITH 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS unserviceable_no_seq START WITH 1")

    op.create_table(
        "stock_verifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("verification_no", sa.String(50), nullable=False, unique=True),
        sa.Column("verification_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("counted_by", sa.BigInteger(), nullable=True),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_by", sa.BigInteger(), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.BigInteger(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["counted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["authorized_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status in ('OPEN','COUNTED','AUTHORIZED','CLOSED','CANCELLED')",
            name="ck_stock_verifications_status_valid",
        ),
    )
    op.create_index("ix_stock_verifications_store_status", "stock_verifications", ["store_id", "status"])
    op.create_index("ix_stock_verifications_fy_date", "stock_verifications", ["financial_year_id", "verification_date"])

    op.create_table(
        "stock_verification_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("verification_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("system_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("physical_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("variance_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["verification_id"], ["stock_verifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("verification_id", "item_id", name="uq_stock_verification_lines_verification_item"),
        sa.CheckConstraint("system_quantity >= 0", name="ck_stock_verification_system_nonnegative"),
        sa.CheckConstraint("physical_quantity >= 0", name="ck_stock_verification_physical_nonnegative"),
    )
    op.create_index("ix_stock_verification_lines_item", "stock_verification_lines", ["item_id"])

    op.create_table(
        "adjustments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("adjustment_no", sa.String(50), nullable=False, unique=True),
        sa.Column("adjustment_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("verification_id", sa.BigInteger(), nullable=False),
        sa.Column("adjustment_type", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("authorized_by", sa.BigInteger(), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verification_id"], ["stock_verifications.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["authorized_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("adjustment_type in ('ADJUSTMENT_IN','ADJUSTMENT_OUT')", name="ck_adjustments_type_valid"),
        sa.CheckConstraint("status in ('OPEN','AUTHORIZED','POSTED','CANCELLED')", name="ck_adjustments_status_valid"),
        sa.UniqueConstraint("verification_id", "adjustment_type", name="uq_adjustments_verification_type"),
    )
    op.create_index("ix_adjustments_store_status", "adjustments", ["store_id", "status"])
    op.create_index("ix_adjustments_verification", "adjustments", ["verification_id"])

    op.create_table(
        "adjustment_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("adjustment_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["adjustment_id"], ["adjustments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("adjustment_id", "item_id", name="uq_adjustment_lines_adjustment_item"),
        sa.CheckConstraint("quantity > 0", name="ck_adjustment_line_quantity_positive"),
    )
    op.create_index("ix_adjustment_lines_item", "adjustment_lines", ["item_id"])

    op.create_table(
        "unserviceable_materials",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("reference_no", sa.String(50), nullable=False, unique=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("reported_by", sa.BigInteger(), nullable=False),
        sa.Column("verified_by", sa.BigInteger(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_by", sa.BigInteger(), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reported_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["authorized_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status in ('REPORTED','VERIFIED','AUTHORIZED','POSTED','CANCELLED')", name="ck_unserviceable_status_valid"),
    )
    op.create_index("ix_unserviceable_store_status", "unserviceable_materials", ["store_id", "status"])
    op.create_index("ix_unserviceable_fy_date", "unserviceable_materials", ["financial_year_id", "date"])

    op.create_table(
        "unserviceable_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("unserviceable_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["unserviceable_id"], ["unserviceable_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("unserviceable_id", "item_id", name="uq_unserviceable_lines_material_item"),
        sa.CheckConstraint("quantity > 0", name="ck_unserviceable_line_quantity_positive"),
    )
    op.create_index("ix_unserviceable_lines_item", "unserviceable_lines", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_unserviceable_lines_item", table_name="unserviceable_lines")
    op.drop_table("unserviceable_lines")
    op.drop_index("ix_unserviceable_store_status", table_name="unserviceable_materials")
    op.drop_index("ix_unserviceable_fy_date", table_name="unserviceable_materials")
    op.drop_table("unserviceable_materials")
    op.drop_index("ix_adjustment_lines_item", table_name="adjustment_lines")
    op.drop_table("adjustment_lines")
    op.drop_index("ix_adjustments_verification", table_name="adjustments")
    op.drop_index("ix_adjustments_store_status", table_name="adjustments")
    op.drop_table("adjustments")
    op.drop_index("ix_stock_verification_lines_item", table_name="stock_verification_lines")
    op.drop_table("stock_verification_lines")
    op.drop_index("ix_stock_verifications_fy_date", table_name="stock_verifications")
    op.drop_index("ix_stock_verifications_store_status", table_name="stock_verifications")
    op.drop_table("stock_verifications")
    op.execute("DROP SEQUENCE IF EXISTS unserviceable_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS adjustment_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS stock_verification_no_seq")
