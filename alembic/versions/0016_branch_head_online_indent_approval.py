"""Ensure branch heads can approve online indents.

Revision ID: 0016_branch_head_online_indent_approval
Revises: 0015_opening_stock_one_per_store_fy
"""
from alembic import op
from sqlalchemy import text

revision = "0016_branch_head_online_indent_approval"
down_revision = "0015_opening_stock_one_per_store_fy"
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'BRANCH_HEAD'
          AND p.code = 'INDENT_APPROVE'
        ON CONFLICT DO NOTHING
    """))

def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'BRANCH_HEAD')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'INDENT_APPROVE')
    """))
