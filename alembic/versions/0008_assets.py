"""add asset register and asset receipt linkage

Revision ID: 0008_assets
Revises: 0007_stock_control
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_assets"
down_revision = "0007_stock_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS asset_no_seq START WITH 1")

    op.create_table(
        "assets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("asset_no", sa.String(50), nullable=False, unique=True),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("serial_no", sa.String(150), nullable=True),
        sa.Column("current_store_id", sa.BigInteger(), nullable=True),
        sa.Column("current_office_id", sa.BigInteger(), nullable=True),
        sa.Column("current_section_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="IN_STOCK"),
        sa.Column("acquisition_financial_year_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('IN_STOCK','ASSIGNED','UNDER_REPAIR','UNSERVICEABLE','DISPOSED','LOST')",
            name="ck_assets_status_valid",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["current_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["current_office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["current_section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["acquisition_financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
    )

    # Serial numbers are unique when present, but assets without serials are allowed.
    op.create_index(
        "uq_assets_serial_no_nonnull",
        "assets",
        ["serial_no"],
        unique=True,
        postgresql_where=sa.text("serial_no IS NOT NULL"),
    )
    op.create_index("ix_assets_item_id", "assets", ["item_id"])
    op.create_index("ix_assets_current_store_id", "assets", ["current_store_id"])
    op.create_index("ix_assets_current_office_id", "assets", ["current_office_id"])
    op.create_index("ix_assets_current_section_id", "assets", ["current_section_id"])
    op.create_index("ix_assets_status", "assets", ["status"])

    op.create_table(
        "asset_details",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("asset_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("make", sa.String(150), nullable=True),
        sa.Column("model", sa.String(150), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_reference", sa.String(100), nullable=True),
        sa.Column("purchase_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("warranty_expiry_date", sa.Date(), nullable=True),
        sa.Column("technical_specifications", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "asset_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("movement_type", sa.String(30), nullable=False),
        sa.Column("from_store_id", sa.BigInteger(), nullable=True),
        sa.Column("to_store_id", sa.BigInteger(), nullable=True),
        sa.Column("from_office_id", sa.BigInteger(), nullable=True),
        sa.Column("from_section_id", sa.BigInteger(), nullable=True),
        sa.Column("to_office_id", sa.BigInteger(), nullable=True),
        sa.Column("to_section_id", sa.BigInteger(), nullable=True),
        sa.Column("reference_type", sa.String(40), nullable=True),
        sa.Column("reference_id", sa.BigInteger(), nullable=True),
        sa.Column("reference_document", sa.String(100), nullable=True),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "movement_type in ('RECEIPT','ASSIGNMENT','TRANSFER','RETURN','REPAIR','UNSERVICEABLE','DISPOSAL','LOST','LOCATION_CHANGE')",
            name="ck_asset_movements_type_valid",
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["from_section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_asset_movements_asset_date", "asset_movements", ["asset_id", "movement_date"])
    op.create_index("ix_asset_movements_reference", "asset_movements", ["reference_type", "reference_id"])

    # Add asset_details JSONB to receipt_lines
    op.add_column(
        "receipt_lines",
        sa.Column("asset_details", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "receipt_line_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("receipt_line_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("receipt_line_id", "asset_id", name="uq_receipt_line_assets_line_asset"),
        sa.ForeignKeyConstraint(["receipt_line_id"], ["receipt_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_receipt_line_assets_asset_id", "receipt_line_assets", ["asset_id"])


def downgrade() -> None:
    op.drop_index("ix_receipt_line_assets_asset_id", table_name="receipt_line_assets")
    op.drop_table("receipt_line_assets")
    op.drop_index("ix_asset_movements_reference", table_name="asset_movements")
    op.drop_index("ix_asset_movements_asset_date", table_name="asset_movements")
    op.drop_table("asset_movements")
    op.drop_table("asset_details")
    op.drop_index("ix_assets_status", table_name="assets")
    op.drop_index("ix_assets_current_section_id", table_name="assets")
    op.drop_index("ix_assets_current_office_id", table_name="assets")
    op.drop_index("ix_assets_current_store_id", table_name="assets")
    op.drop_index("ix_assets_item_id", table_name="assets")
    op.drop_index("uq_assets_serial_no_nonnull", table_name="assets")
    op.drop_table("assets")

    # Drop asset_details from receipt_lines
    op.drop_column("receipt_lines", "asset_details")
