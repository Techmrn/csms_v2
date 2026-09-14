"""add master and user administration permissions

Revision ID: 0013_master_user_admin_permissions
Revises: 0012_opening_stock_permission
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_master_user_admin_permissions"
down_revision = "0012_opening_stock_permission"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("MASTER_DATA_MANAGE", "Manage master data", "MASTER", "MANAGE"),
    ("ORGANIZATION_MANAGE", "Manage offices, stores and sections", "ORGANIZATION", "MANAGE"),
    ("USER_MANAGE", "Manage users, roles and store assignments", "USER", "MANAGE"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Alembic's default PostgreSQL version column is VARCHAR(32). This revision
    # ID is intentionally descriptive and exceeds 32 characters, so widen the
    # version column before Alembic records this revision.
    conn.execute(
        sa.text(
            "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(100)"
        )
    )
    for code, name, module, action in PERMISSIONS:
        conn.execute(
            sa.text(
                """INSERT INTO permissions (code, name, module, action, is_active, created_at, updated_at)
                   VALUES (:code, :name, :module, :action, TRUE, NOW(), NOW())
                   ON CONFLICT (code) DO NOTHING"""
            ),
            dict(code=code, name=name, module=module, action=action),
        )

    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id
               FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'SYSTEM_ADMIN'
                 AND p.code IN ('MASTER_DATA_MANAGE','ORGANIZATION_MANAGE','USER_MANAGE')
               ON CONFLICT DO NOTHING"""
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """DELETE FROM role_permissions
               WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('MASTER_DATA_MANAGE','ORGANIZATION_MANAGE','USER_MANAGE'))
                 AND role_id IN (SELECT id FROM roles WHERE code='SYSTEM_ADMIN')"""
        )
    )
    conn.execute(
        sa.text("DELETE FROM permissions WHERE code IN ('MASTER_DATA_MANAGE','ORGANIZATION_MANAGE','USER_MANAGE')")
    )
