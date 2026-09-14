"""ensure opening stock permission and storekeeper assignments

Revision ID: 0012_opening_stock_permission
Revises: 0011_manual_opening_assets
Create Date: 2026-09-13 17:00:00
"""

from alembic import op

revision = "0012_opening_stock_permission"
down_revision = "0011_manual_opening_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (code, name, module, action, is_active, created_at, updated_at)
        SELECT 'STOCK_OPENING_CREATE', 'Enter and post opening stock', 'STOCK', 'OPENING_CREATE', TRUE, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'STOCK_OPENING_CREATE')
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.code IN ('GENERAL_STOREKEEPER','ASSISTANT_STOREKEEPER','BRANCH_STOREKEEPER')
          AND p.code = 'STOCK_OPENING_CREATE'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id = (SELECT id FROM permissions WHERE code = 'STOCK_OPENING_CREATE')
          AND role_id IN (SELECT id FROM roles WHERE code IN ('GENERAL_STOREKEEPER','ASSISTANT_STOREKEEPER','BRANCH_STOREKEEPER'))
    """)
    op.execute("""
        DELETE FROM permissions WHERE code = 'STOCK_OPENING_CREATE'
    """)
