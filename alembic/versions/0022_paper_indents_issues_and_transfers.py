"""Paper indents, issues, and inter-press transfers.

Revision ID: 0022_paper_indents_issues_and_transfers
Revises: 0021_paper_store_foundation_and_receipts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0022_paper_indents_issues_and_transfers"
down_revision = "0021_paper_store_foundation_and_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create paper_indents table
    op.create_table(
        "paper_indents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("indent_no", sa.String(50), nullable=False, unique=True),
        sa.Column("indent_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_no", sa.String(100), nullable=True),
        sa.Column("request_source", sa.String(20), nullable=False, server_default="PHYSICAL"),
        sa.Column("status", sa.String(30), nullable=False, server_default="FINALIZED"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("request_source in ('PHYSICAL', 'ONLINE')", name="ck_paper_indent_source_valid"),
        sa.CheckConstraint(
            "status in ('RECORDED', 'SUBMITTED', 'APPROVED', 'FINALIZED', 'REJECTED', 'CANCELLED')",
            name="ck_paper_indent_status_valid",
        ),
    )

    # 2. Create paper_indent_lines table
    op.create_table(
        "paper_indent_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("indent_id", sa.BigInteger(), sa.ForeignKey("paper_indents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("issued_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("remarks", sa.String(255), nullable=True),
        sa.UniqueConstraint("indent_id", "paper_item_id", name="uq_paper_indent_lines_indent_item"),
        sa.CheckConstraint("requested_quantity > 0", name="ck_paper_indent_line_req_qty_pos"),
        sa.CheckConstraint(
            "approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity)",
            name="ck_paper_indent_line_app_qty_valid",
        ),
        sa.CheckConstraint(
            "issued_quantity is null or issued_quantity >= 0",
            name="ck_paper_indent_line_iss_qty_nonneg",
        ),
    )

    # 3. Create paper_issues table
    op.create_table(
        "paper_issues",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("issue_no", sa.String(50), nullable=False, unique=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("indent_id", sa.BigInteger(), sa.ForeignKey("paper_indents.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="FINALIZED"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 4. Create paper_issue_lines table
    op.create_table(
        "paper_issue_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("issue_id", sa.BigInteger(), sa.ForeignKey("paper_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("remarks", sa.String(255), nullable=True),
        sa.CheckConstraint("quantity >= 0", name="ck_paper_issue_line_qty_nonneg"),
        sa.CheckConstraint("weight_kg >= 0", name="ck_paper_issue_line_wt_nonneg"),
    )

    # 5. Create paper_transfers table
    op.create_table(
        "paper_transfers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("transfer_no", sa.String(50), nullable=False, unique=True),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transfer_mode", sa.String(20), nullable=False, server_default="PULL"),
        sa.Column("status", sa.String(30), nullable=False, server_default="SUBMITTED"),
        sa.Column("vehicle_no", sa.String(50), nullable=True),
        sa.Column("driver_name", sa.String(100), nullable=True),
        sa.Column("carrier_name", sa.String(100), nullable=True),
        sa.Column("gate_pass_no", sa.String(50), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch_approved_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("branch_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("directorate_approved_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("directorate_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_posting_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("receive_posting_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source_store_id <> destination_store_id", name="ck_paper_transfer_src_dst_different"),
        sa.CheckConstraint("transfer_mode in ('PULL', 'PUSH')", name="ck_paper_transfer_mode_valid"),
        sa.CheckConstraint(
            "status in ('SUBMITTED', 'DIRECTORATE_DIRECTIVE', 'BRANCH_APPROVED', 'DISPATCHED', 'RECEIVED', 'DISCREPANCY', 'CLOSED', 'REJECTED', 'CANCELLED')",
            name="ck_paper_transfer_status_valid",
        ),
    )

    # 6. Create paper_transfer_lines table
    op.create_table(
        "paper_transfer_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("transfer_id", sa.BigInteger(), sa.ForeignKey("paper_transfers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("dispatched_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("remarks", sa.String(255), nullable=True),
        sa.CheckConstraint("requested_quantity > 0", name="ck_paper_transfer_line_req_qty_pos"),
        sa.CheckConstraint("dispatched_quantity >= 0", name="ck_paper_transfer_line_disp_qty_nonneg"),
        sa.CheckConstraint("received_quantity >= 0", name="ck_paper_transfer_line_recv_qty_nonneg"),
        sa.CheckConstraint("weight_kg >= 0", name="ck_paper_transfer_line_wt_nonneg"),
    )

    # 7. Seed second Branch Press for inter-press transfers
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """INSERT INTO offices (code, name, office_type, is_active, created_at, updated_at)
               VALUES ('PRESS2', 'Branch Press, Shoranur', 'BRANCH', TRUE, NOW(), NOW())
               ON CONFLICT (code) DO NOTHING"""
        )
    )

    press2_office = conn.execute(
        sa.text("SELECT id FROM offices WHERE code = 'PRESS2' LIMIT 1")
    ).fetchone()

    if press2_office:
        press2_id = press2_office[0]
        # Seed sections for PRESS2
        conn.execute(
            sa.text(
                """INSERT INTO sections (office_id, code, name, is_active, created_at, updated_at)
                   VALUES (:office_id, 'OFFSET', 'Offset Section', TRUE, NOW(), NOW()),
                          (:office_id, 'BINDING', 'Binding Section', TRUE, NOW(), NOW())
                   ON CONFLICT DO NOTHING"""
            ),
            dict(office_id=press2_id),
        )
        # Seed stores for PRESS2
        conn.execute(
            sa.text(
                """INSERT INTO stores (office_id, code, name, store_type, is_primary, remarks, is_active, created_at, updated_at)
                   VALUES (:office_id, 'PRESS2-STORE', 'Branch Press General Store', 'BRANCH', TRUE, 'General Store', TRUE, NOW(), NOW()),
                          (:office_id, 'BP-PAPER-WH', 'Branch Press Paper Warehouse', 'PAPER_WAREHOUSE', FALSE, 'Branch Paper Warehouse', TRUE, NOW(), NOW())
                   ON CONFLICT (code) DO NOTHING"""
            ),
            dict(office_id=press2_id),
        )


def downgrade() -> None:
    op.drop_table("paper_transfer_lines")
    op.drop_table("paper_transfers")
    op.drop_table("paper_issue_lines")
    op.drop_table("paper_issues")
    op.drop_table("paper_indent_lines")
    op.drop_table("paper_indents")

