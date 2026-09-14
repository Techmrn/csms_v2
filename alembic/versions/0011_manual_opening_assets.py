"""manual opening stock supports assets

Revision ID: 0011_manual_opening_assets
Revises: 0010_merge_asset_phase2_heads
Create Date: 2026-09-13 16:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_manual_opening_assets"
down_revision = "0010_merge_asset_phase2_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opening_stock_lines",
        sa.Column("asset_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.drop_constraint(
        "ck_asset_movements_type_valid",
        "asset_movements",
        type_="check",
    )
    op.create_check_constraint(
        "ck_asset_movements_type_valid",
        "asset_movements",
        "movement_type in ('OPENING','RECEIPT','ASSIGNMENT','TRANSFER','RETURN','REPAIR','UNSERVICEABLE','DISPOSAL','LOST','LOCATION_CHANGE')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_asset_movements_type_valid",
        "asset_movements",
        type_="check",
    )
    op.create_check_constraint(
        "ck_asset_movements_type_valid",
        "asset_movements",
        "movement_type in ('RECEIPT','ASSIGNMENT','TRANSFER','RETURN','REPAIR','UNSERVICEABLE','DISPOSAL','LOST','LOCATION_CHANGE')",
    )
    op.drop_column("opening_stock_lines", "asset_details")
