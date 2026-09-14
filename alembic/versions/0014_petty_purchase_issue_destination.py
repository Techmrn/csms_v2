"""store petty purchase immediate-issue destination

Revision ID: 0014_petty_purchase_issue_destination
Revises: 0013_master_user_admin_permissions
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_petty_purchase_issue_destination"
down_revision = "0013_master_user_admin_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("petty_purchases", sa.Column("issue_office_id", sa.Integer(), nullable=True))
    op.add_column("petty_purchases", sa.Column("issue_section_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_petty_purchases_issue_office", "petty_purchases", "offices", ["issue_office_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_petty_purchases_issue_section", "petty_purchases", "sections", ["issue_section_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_petty_purchases_issue_section", "petty_purchases", type_="foreignkey")
    op.drop_constraint("fk_petty_purchases_issue_office", "petty_purchases", type_="foreignkey")
    op.drop_column("petty_purchases", "issue_section_id")
    op.drop_column("petty_purchases", "issue_office_id")
