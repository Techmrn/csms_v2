"""Add approved_quantity to indent_lines.

Revision ID: 0018_indent_line_approved_quantity
Revises: 0017_legacy_return_support
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_indent_line_approved_quantity"
down_revision = "0017_legacy_return_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("indent_lines", sa.Column("approved_quantity", sa.Numeric(18, 3), nullable=True))
    op.create_check_constraint(
        "ck_indent_lines_approved_quantity_valid",
        "indent_lines",
        "approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_indent_lines_approved_quantity_valid", "indent_lines", type_="check")
    op.drop_column("indent_lines", "approved_quantity")
