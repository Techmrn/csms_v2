"""Add legacy/manual return support.

Revision ID: 0017_legacy_return_support
Revises: 0016_branch_head_online_indent_approval
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_legacy_return_support"
down_revision = "0016_branch_head_online_indent_approval"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column("stock_returns", "original_issue_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("stock_return_lines", "original_issue_line_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("stock_returns", sa.Column("return_type", sa.String(length=20), nullable=False, server_default="CSMS_ISSUE"))
    op.add_column("stock_returns", sa.Column("manual_reference", sa.String(length=100), nullable=True))
    op.add_column("stock_returns", sa.Column("condition", sa.String(length=20), nullable=False, server_default="USABLE"))
    op.add_column("stock_returns", sa.Column("returning_user_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_stock_returns_returning_user", "stock_returns", "users", ["returning_user_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_stock_returns_return_type", "stock_returns", ["return_type"])

def downgrade() -> None:
    op.drop_index("ix_stock_returns_return_type", table_name="stock_returns")
    op.drop_constraint("fk_stock_returns_returning_user", "stock_returns", type_="foreignkey")
    op.drop_column("stock_returns", "returning_user_id")
    op.drop_column("stock_returns", "condition")
    op.drop_column("stock_returns", "manual_reference")
    op.drop_column("stock_returns", "return_type")
    op.alter_column("stock_return_lines", "original_issue_line_id", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("stock_returns", "original_issue_id", existing_type=sa.BigInteger(), nullable=False)
