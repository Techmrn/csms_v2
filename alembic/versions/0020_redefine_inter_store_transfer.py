"""Redefine stock transfers for branch-to-branch, central-to-branch, and directorate push transfers.

Revision ID: 0020_redefine_inter_store_transfer
Revises: 0019_transfer_gate_pass_fields
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_redefine_inter_store_transfer"
down_revision = "0019_transfer_gate_pass_fields"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    ("STOCK_TRANSFER_CREATE", "Create inter-store transfer request or directive", "STOCK", "TRANSFER_CREATE"),
    ("STOCK_TRANSFER_APPROVE_BRANCH", "Approve branch transfer request", "STOCK", "TRANSFER_APPROVE_BRANCH"),
    ("STOCK_TRANSFER_APPROVE_DIRECTORATE", "Approve inter-store transfer or initiate directive", "STOCK", "TRANSFER_APPROVE_DIRECTORATE"),
    ("STOCK_TRANSFER_AUTHORIZE_SUPPLY", "Authorize issue from supplying store", "STOCK", "TRANSFER_AUTHORIZE_SUPPLY"),
]


def upgrade() -> None:
    # 1. Update stock_transfers table
    op.alter_column("stock_transfers", "requisition_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("stock_transfers", sa.Column("transfer_mode", sa.String(20), server_default="PULL", nullable=False))
    
    op.add_column("stock_transfers", sa.Column("branch_approved_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("stock_transfers", sa.Column("branch_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_transfers", sa.Column("directorate_approved_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("stock_transfers", sa.Column("directorate_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_transfers", sa.Column("supply_authorized_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("stock_transfers", sa.Column("supply_authorized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_transfers", sa.Column("rejected_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("stock_transfers", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stock_transfers", sa.Column("rejection_reason", sa.Text(), nullable=True))

    op.drop_constraint("ck_transfer_status_valid", "stock_transfers", type_="check")
    op.create_check_constraint(
        "ck_transfer_status_valid",
        "stock_transfers",
        "status in ('SUBMITTED','BRANCH_APPROVED','DIRECTORATE_APPROVED','SUPPLY_AUTHORIZED','READY_FOR_DISPATCH','APPROVED','DISPATCHED','RECEIVED','DISCREPANCY','CLOSED','REJECTED','CANCELLED')",
    )

    # 2. Update stock_transfer_lines table
    op.alter_column("stock_transfer_lines", "requisition_line_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("stock_transfer_lines", sa.Column("requested_quantity", sa.Numeric(18, 3), nullable=True))
    op.execute("UPDATE stock_transfer_lines SET requested_quantity = quantity WHERE requested_quantity IS NULL")
    op.alter_column("stock_transfer_lines", "requested_quantity", existing_type=sa.Numeric(18, 3), nullable=False)
    op.add_column("stock_transfer_lines", sa.Column("approved_quantity", sa.Numeric(18, 3), nullable=True))
    op.add_column("stock_transfer_lines", sa.Column("received_quantity", sa.Numeric(18, 3), server_default="0", nullable=False))

    op.drop_constraint("ck_transfer_line_quantity_positive", "stock_transfer_lines", type_="check")
    op.create_check_constraint(
        "ck_transfer_line_quantities_valid",
        "stock_transfer_lines",
        "requested_quantity > 0 and quantity >= 0 and received_quantity >= 0 and (approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity))",
    )

    # 3. Seed new permissions and role mappings
    conn = op.get_bind()
    for code, name, module, action in NEW_PERMISSIONS:
        conn.execute(
            sa.text(
                """INSERT INTO permissions (code, name, module, action, is_active, created_at, updated_at)
                   VALUES (:code, :name, :module, :action, TRUE, NOW(), NOW())
                   ON CONFLICT (code) DO NOTHING"""
            ),
            dict(code=code, name=name, module=module, action=action),
        )

    # Grant branch storekeepers dispatch permission for when branch is the source of transfer
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'BRANCH_STOREKEEPER' AND p.code = 'STOCK_TRANSFER_DISPATCH'
               ON CONFLICT DO NOTHING"""
        )
    )

    # Map STOCK_TRANSFER_CREATE to storekeepers & deputy
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code IN ('BRANCH_STOREKEEPER', 'GENERAL_STOREKEEPER', 'ASSISTANT_STOREKEEPER', 'DEPUTY_SUPDT_STORES')
                 AND p.code = 'STOCK_TRANSFER_CREATE'
               ON CONFLICT DO NOTHING"""
        )
    )

    # Map STOCK_TRANSFER_APPROVE_BRANCH to branch head
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'BRANCH_HEAD' AND p.code = 'STOCK_TRANSFER_APPROVE_BRANCH'
               ON CONFLICT DO NOTHING"""
        )
    )

    # Map STOCK_TRANSFER_APPROVE_DIRECTORATE to deputy superintendent
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'DEPUTY_SUPDT_STORES' AND p.code = 'STOCK_TRANSFER_APPROVE_DIRECTORATE'
               ON CONFLICT DO NOTHING"""
        )
    )

    # Map STOCK_TRANSFER_AUTHORIZE_SUPPLY to branch head and deputy superintendent
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code IN ('BRANCH_HEAD', 'DEPUTY_SUPDT_STORES') AND p.code = 'STOCK_TRANSFER_AUTHORIZE_SUPPLY'
               ON CONFLICT DO NOTHING"""
        )
    )


def downgrade() -> None:
    op.drop_constraint("ck_transfer_line_quantities_valid", "stock_transfer_lines", type_="check")
    op.create_check_constraint(
        "ck_transfer_line_quantity_positive",
        "stock_transfer_lines",
        "quantity > 0",
    )
    op.drop_column("stock_transfer_lines", "received_quantity")
    op.drop_column("stock_transfer_lines", "approved_quantity")
    op.drop_column("stock_transfer_lines", "requested_quantity")
    op.alter_column("stock_transfer_lines", "requisition_line_id", existing_type=sa.BigInteger(), nullable=False)

    op.drop_constraint("ck_transfer_status_valid", "stock_transfers", type_="check")
    op.create_check_constraint(
        "ck_transfer_status_valid",
        "stock_transfers",
        "status in ('APPROVED','DISPATCHED','RECEIVED','DISCREPANCY','CLOSED','CANCELLED')",
    )
    op.drop_column("stock_transfers", "rejection_reason")
    op.drop_column("stock_transfers", "rejected_at")
    op.drop_column("stock_transfers", "rejected_by")
    op.drop_column("stock_transfers", "supply_authorized_at")
    op.drop_column("stock_transfers", "supply_authorized_by")
    op.drop_column("stock_transfers", "directorate_approved_at")
    op.drop_column("stock_transfers", "directorate_approved_by")
    op.drop_column("stock_transfers", "branch_approved_at")
    op.drop_column("stock_transfers", "branch_approved_by")
    op.drop_column("stock_transfers", "transfer_mode")
    op.alter_column("stock_transfers", "requisition_id", existing_type=sa.BigInteger(), nullable=False)
