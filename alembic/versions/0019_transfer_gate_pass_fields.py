"""Add vehicle_no and received_by_name to stock_transfers for outward gate pass.

Revision ID: 0019_transfer_gate_pass_fields
Revises: 0018_indent_line_approved_quantity
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_transfer_gate_pass_fields"
down_revision = "0018_indent_line_approved_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_transfers", sa.Column("vehicle_no", sa.String(length=50), nullable=True))
    op.add_column("stock_transfers", sa.Column("received_by_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_transfers", "received_by_name")
    op.drop_column("stock_transfers", "vehicle_no")
