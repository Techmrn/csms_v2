"""Separate warehouse roles, paper opening stock, FY carryover, and Reams+Sheets / KG units.

Revision ID: 0023_warehouse_separation_opening_and_sheets
Revises: 0022_paper_indents_issues_and_transfers
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0023_warehouse_separation_opening_and_sheets"
down_revision = "0022_paper_indents_issues_and_transfers"
branch_labels = None
depends_on = None


NEW_PAPER_PERMISSIONS = [
    ("PAPER_OPENING_CREATE", "Enter and post warehouse opening stock", "PAPER", "OPENING_CREATE"),
    ("PAPER_REGISTER_VIEW", "View paper warehouse registers and reports", "PAPER", "REGISTER_VIEW"),
]


def upgrade() -> None:
    # 1. paper_items: add sheets_per_ream (configurable, default 500)
    op.add_column(
        "paper_items",
        sa.Column("sheets_per_ream", sa.Integer(), nullable=False, server_default="500"),
    )
    op.create_check_constraint(
        "ck_paper_items_sheets_per_ream_positive",
        "paper_items",
        "sheets_per_ream > 0",
    )

    # 2. paper_stock_movements: add exact integer sheet columns + update direction check constraint
    op.add_column(
        "paper_stock_movements",
        sa.Column("sheets_in", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_stock_movements",
        sa.Column("sheets_out", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_paper_sheets_in_nonnegative", "paper_stock_movements", "sheets_in >= 0"
    )
    op.create_check_constraint(
        "ck_paper_sheets_out_nonnegative", "paper_stock_movements", "sheets_out >= 0"
    )

    # Backfill sheets_in / sheets_out for existing SHEET movements, and weight_kg for REEL
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """UPDATE paper_stock_movements m
               SET sheets_in = ROUND(m.quantity_in * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   sheets_out = ROUND(m.quantity_out * COALESCE(pi.sheets_per_ream, 500))::bigint
               FROM paper_items pi
               WHERE m.paper_item_id = pi.id AND pi.form_type = 'SHEET'"""
        )
    )
    conn.execute(
        sa.text(
            """UPDATE paper_stock_movements m
               SET weight_kg_in = CASE WHEN m.weight_kg_in = 0 AND m.quantity_in > 0 THEN m.quantity_in ELSE m.weight_kg_in END,
                   weight_kg_out = CASE WHEN m.weight_kg_out = 0 AND m.quantity_out > 0 THEN m.quantity_out ELSE m.weight_kg_out END
               FROM paper_items pi
               WHERE m.paper_item_id = pi.id AND pi.form_type = 'REEL'"""
        )
    )

    op.drop_constraint(
        "ck_paper_exactly_one_quantity_direction",
        "paper_stock_movements",
        type_="check",
    )
    op.create_check_constraint(
        "ck_paper_exactly_one_direction",
        "paper_stock_movements",
        "(((sheets_in > 0 OR weight_kg_in > 0) AND sheets_out = 0 AND weight_kg_out = 0) "
        "OR ((sheets_out > 0 OR weight_kg_out > 0) AND sheets_in = 0 AND weight_kg_in = 0))",
    )

    # 3. paper_receipt_lines: add exact sheet columns and relax decimal quantity checks
    for col in ("challan_sheets", "received_sheets", "accepted_sheets", "damaged_sheets"):
        op.add_column(
            "paper_receipt_lines",
            sa.Column(col, sa.BigInteger(), nullable=False, server_default="0"),
        )
    conn.execute(
        sa.text(
            """UPDATE paper_receipt_lines l
               SET challan_sheets = ROUND(l.challan_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   received_sheets = ROUND(l.received_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   accepted_sheets = ROUND(l.accepted_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   damaged_sheets = ROUND(l.damaged_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint
               FROM paper_items pi
               WHERE l.paper_item_id = pi.id AND pi.form_type = 'SHEET'"""
        )
    )
    op.drop_constraint(
        "ck_paper_receipt_line_received_qty_pos", "paper_receipt_lines", type_="check"
    )
    op.create_check_constraint(
        "ck_paper_receipt_line_received_valid",
        "paper_receipt_lines",
        "received_sheets > 0 OR weight_kg > 0 OR received_quantity > 0",
    )
    op.create_check_constraint(
        "ck_paper_receipt_line_sheets_valid",
        "paper_receipt_lines",
        "challan_sheets >= 0 AND received_sheets >= 0 AND accepted_sheets >= 0 "
        "AND damaged_sheets >= 0 AND (accepted_sheets + damaged_sheets <= received_sheets)",
    )

    # 4. paper_indent_lines: add sheet & weight columns
    op.add_column("paper_indent_lines", sa.Column("requested_sheets", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("paper_indent_lines", sa.Column("approved_sheets", sa.BigInteger(), nullable=True))
    op.add_column("paper_indent_lines", sa.Column("issued_sheets", sa.BigInteger(), nullable=True))
    op.add_column("paper_indent_lines", sa.Column("requested_weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"))
    op.add_column("paper_indent_lines", sa.Column("approved_weight_kg", sa.Numeric(18, 3), nullable=True))
    op.add_column("paper_indent_lines", sa.Column("issued_weight_kg", sa.Numeric(18, 3), nullable=True))

    conn.execute(
        sa.text(
            """UPDATE paper_indent_lines l
               SET requested_sheets = ROUND(l.requested_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   approved_sheets = CASE WHEN l.approved_quantity IS NOT NULL THEN ROUND(l.approved_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint ELSE NULL END,
                   issued_sheets = CASE WHEN l.issued_quantity IS NOT NULL THEN ROUND(l.issued_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint ELSE NULL END
               FROM paper_items pi
               WHERE l.paper_item_id = pi.id AND pi.form_type = 'SHEET'"""
        )
    )
    conn.execute(
        sa.text(
            """UPDATE paper_indent_lines l
               SET requested_weight_kg = l.requested_quantity,
                   approved_weight_kg = l.approved_quantity,
                   issued_weight_kg = l.issued_quantity
               FROM paper_items pi
               WHERE l.paper_item_id = pi.id AND pi.form_type = 'REEL'"""
        )
    )

    op.drop_constraint("ck_paper_indent_line_req_qty_pos", "paper_indent_lines", type_="check")
    op.drop_constraint("ck_paper_indent_line_app_qty_valid", "paper_indent_lines", type_="check")
    op.create_check_constraint(
        "ck_paper_indent_line_req_valid",
        "paper_indent_lines",
        "requested_sheets > 0 OR requested_weight_kg > 0 OR requested_quantity > 0",
    )

    # 5. paper_issue_lines: add sheets
    op.add_column("paper_issue_lines", sa.Column("sheets", sa.BigInteger(), nullable=False, server_default="0"))
    conn.execute(
        sa.text(
            """UPDATE paper_issue_lines l
               SET sheets = ROUND(l.quantity * COALESCE(pi.sheets_per_ream, 500))::bigint
               FROM paper_items pi
               WHERE l.paper_item_id = pi.id AND pi.form_type = 'SHEET'"""
        )
    )

    # 6. paper_transfer_lines: add sheet & weight columns
    op.add_column("paper_transfer_lines", sa.Column("requested_sheets", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("paper_transfer_lines", sa.Column("approved_sheets", sa.BigInteger(), nullable=True))
    op.add_column("paper_transfer_lines", sa.Column("dispatched_sheets", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("paper_transfer_lines", sa.Column("received_sheets", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("paper_transfer_lines", sa.Column("requested_weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"))
    op.add_column("paper_transfer_lines", sa.Column("dispatched_weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"))
    op.add_column("paper_transfer_lines", sa.Column("received_weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"))

    conn.execute(
        sa.text(
            """UPDATE paper_transfer_lines l
               SET requested_sheets = ROUND(l.requested_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   approved_sheets = CASE WHEN l.approved_quantity IS NOT NULL THEN ROUND(l.approved_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint ELSE NULL END,
                   dispatched_sheets = ROUND(l.dispatched_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint,
                   received_sheets = ROUND(l.received_quantity * COALESCE(pi.sheets_per_ream, 500))::bigint
               FROM paper_items pi
               WHERE l.paper_item_id = pi.id AND pi.form_type = 'SHEET'"""
        )
    )
    conn.execute(
        sa.text(
            """UPDATE paper_transfer_lines l
               SET requested_weight_kg = l.requested_quantity,
                   dispatched_weight_kg = l.weight_kg,
                   received_weight_kg = CASE WHEN l.received_quantity > 0 AND l.weight_kg > 0 THEN l.weight_kg ELSE l.received_quantity END
               FROM paper_items pi
               WHERE l.paper_item_id = pi.id AND pi.form_type = 'REEL'"""
        )
    )
    op.drop_constraint("ck_paper_transfer_line_req_qty_pos", "paper_transfer_lines", type_="check")
    op.create_check_constraint(
        "ck_paper_transfer_line_req_valid",
        "paper_transfer_lines",
        "requested_sheets > 0 OR requested_weight_kg > 0 OR requested_quantity > 0",
    )

    # 7. Paper Opening Stock tables + opening_type on General opening_stocks
    op.add_column(
        "opening_stocks",
        sa.Column("opening_type", sa.String(20), nullable=False, server_default="INITIAL"),
    )
    op.add_column(
        "opening_stocks",
        sa.Column(
            "source_financial_year_id",
            sa.Integer(),
            sa.ForeignKey("financial_years.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    op.create_table(
        "paper_opening_stocks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opening_no", sa.String(50), nullable=False, unique=True),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("opening_type", sa.String(20), nullable=False, server_default="INITIAL"),
        sa.Column("source_financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("opening_type in ('INITIAL', 'CARRY_FORWARD')", name="ck_paper_opening_type_valid"),
        sa.CheckConstraint("status in ('OPEN', 'POSTED', 'CANCELLED')", name="ck_paper_opening_status_valid"),
    )

    op.create_table(
        "paper_opening_stock_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opening_stock_id", sa.BigInteger(), sa.ForeignKey("paper_opening_stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("total_sheets", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("reel_count", sa.Integer(), nullable=True),
        sa.Column("remarks", sa.String(255), nullable=True),
        sa.UniqueConstraint("opening_stock_id", "paper_item_id", name="uq_paper_opening_line_opening_item"),
        sa.CheckConstraint("total_sheets >= 0 AND weight_kg >= 0", name="ck_paper_opening_line_nonneg"),
        sa.CheckConstraint("total_sheets > 0 OR weight_kg > 0", name="ck_paper_opening_line_positive"),
    )

    # 8. Role & Permission Isolation: Dedicated WAREHOUSEMAN role, Strip PAPER_* from Storekeepers
    for code, name, module, action in NEW_PAPER_PERMISSIONS:
        conn.execute(
            sa.text(
                """INSERT INTO permissions (code, name, module, action, is_active, created_at, updated_at)
                   VALUES (:code, :name, :module, :action, TRUE, NOW(), NOW())
                   ON CONFLICT (code) DO NOTHING"""
            ),
            dict(code=code, name=name, module=module, action=action),
        )

    # Insert WAREHOUSEMAN role
    conn.execute(
        sa.text(
            """INSERT INTO roles (code, name, is_active, created_at, updated_at)
               VALUES ('WAREHOUSEMAN', 'Paper Warehouseman', TRUE, NOW(), NOW())
               ON CONFLICT (code) DO NOTHING"""
        )
    )

    # Assign WAREHOUSEMAN permissions
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'WAREHOUSEMAN'
                 AND p.code IN (
                     'PAPER_VIEW', 'PAPER_OPENING_CREATE', 'PAPER_RECEIPT_CREATE',
                     'PAPER_RECEIPT_POST', 'PAPER_ISSUE', 'PAPER_TRANSFER_CREATE',
                     'PAPER_TRANSFER_DISPATCH', 'PAPER_TRANSFER_RECEIVE', 'PAPER_REGISTER_VIEW'
                 )
               ON CONFLICT DO NOTHING"""
        )
    )

    # Assign PAPER_REGISTER_VIEW to supervisory roles & admin
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code IN ('SYSTEM_ADMIN', 'DIRECTOR', 'DEPUTY_SUPDT_STORES', 'BRANCH_HEAD')
                 AND p.code = 'PAPER_REGISTER_VIEW'
               ON CONFLICT DO NOTHING"""
        )
    )

    # Ensure SECTION_USER holds PAPER_VIEW and PAPER_INDENT_CREATE
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'SECTION_USER'
                 AND p.code IN ('PAPER_VIEW', 'PAPER_INDENT_CREATE')
               ON CONFLICT DO NOTHING"""
        )
    )

    # Strip all PAPER_* permissions from Storekeeper roles!
    conn.execute(
        sa.text(
            """DELETE FROM role_permissions
               WHERE role_id IN (
                   SELECT id FROM roles WHERE code IN ('GENERAL_STOREKEEPER', 'ASSISTANT_STOREKEEPER', 'BRANCH_STOREKEEPER')
               )
               AND permission_id IN (
                   SELECT id FROM permissions WHERE code LIKE 'PAPER_%'
               )"""
        )
    )

    # Detach Storekeeper-only users from PAPER_WAREHOUSE assignments in user_stores
    conn.execute(
        sa.text(
            """DELETE FROM user_stores us
               USING stores s
               WHERE us.store_id = s.id
                 AND s.store_type = 'PAPER_WAREHOUSE'
                 AND NOT EXISTS (
                     SELECT 1 FROM user_roles ur
                     JOIN roles r ON r.id = ur.role_id
                     WHERE ur.user_id = us.user_id AND r.code = 'WAREHOUSEMAN'
                 )"""
        )
    )

    # Seed dedicated dev Warehousemen for Central Press & Branch Press evenly if dev users exist
    whman_role = conn.execute(sa.text("SELECT id FROM roles WHERE code = 'WAREHOUSEMAN' LIMIT 1")).fetchone()
    sample_dev = conn.execute(sa.text("SELECT password_hash FROM users WHERE username = 'dev_press_sk' LIMIT 1")).fetchone()
    if whman_role and sample_dev:
        whman_role_id = whman_role[0]
        pwd_hash = sample_dev[0]

        for ucode, uname, fname, office_code, wh_code in [
            ("DEV-CP-WHM", "dev_cp_whman", "Central Press Warehouseman (DEV)", "PRESS", "PRESS-PAPER-WH"),
            ("DEV-BP-WHM", "dev_bp_whman", "Branch Press Warehouseman (DEV)", "PRESS2", "BP-PAPER-WH"),
        ]:
            office_row = conn.execute(sa.text("SELECT id FROM offices WHERE code = :c LIMIT 1"), dict(c=office_code)).fetchone()
            store_row = conn.execute(sa.text("SELECT id FROM stores WHERE code = :c LIMIT 1"), dict(c=wh_code)).fetchone()
            if office_row and store_row:
                conn.execute(
                    sa.text(
                        """INSERT INTO users (code, username, password_hash, full_name, designation, office_id, is_active, created_at, updated_at)
                           VALUES (:ucode, :uname, :phash, :fname, 'Paper Warehouseman', :oid, TRUE, NOW(), NOW())
                           ON CONFLICT (username) DO NOTHING"""
                    ),
                    dict(ucode=ucode, uname=uname, phash=pwd_hash, fname=fname, oid=office_row[0]),
                )
                u_row = conn.execute(sa.text("SELECT id FROM users WHERE username = :uname LIMIT 1"), dict(uname=uname)).fetchone()
                if u_row:
                    conn.execute(
                        sa.text(
                            """INSERT INTO user_roles (user_id, role_id)
                               VALUES (:uid, :rid) ON CONFLICT DO NOTHING"""
                        ),
                        dict(uid=u_row[0], rid=whman_role_id),
                    )
                    conn.execute(
                        sa.text(
                            """INSERT INTO user_stores (user_id, store_id, is_primary)
                               VALUES (:uid, :sid, TRUE) ON CONFLICT DO NOTHING"""
                        ),
                        dict(uid=u_row[0], sid=store_row[0]),
                    )


def downgrade() -> None:
    op.drop_table("paper_opening_stock_lines")
    op.drop_table("paper_opening_stocks")
    op.drop_column("opening_stocks", "source_financial_year_id")
    op.drop_column("opening_stocks", "opening_type")

    op.drop_constraint("ck_paper_transfer_line_req_valid", "paper_transfer_lines", type_="check")
    op.create_check_constraint("ck_paper_transfer_line_req_qty_pos", "paper_transfer_lines", "requested_quantity > 0")
    for col in ("received_weight_kg", "dispatched_weight_kg", "requested_weight_kg", "received_sheets", "dispatched_sheets", "approved_sheets", "requested_sheets"):
        op.drop_column("paper_transfer_lines", col)

    op.drop_column("paper_issue_lines", "sheets")

    op.drop_constraint("ck_paper_indent_line_req_valid", "paper_indent_lines", type_="check")
    op.create_check_constraint("ck_paper_indent_line_req_qty_pos", "paper_indent_lines", "requested_quantity > 0")
    op.create_check_constraint(
        "ck_paper_indent_line_app_qty_valid",
        "paper_indent_lines",
        "approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity)",
    )
    for col in ("issued_weight_kg", "approved_weight_kg", "requested_weight_kg", "issued_sheets", "approved_sheets", "requested_sheets"):
        op.drop_column("paper_indent_lines", col)

    op.drop_constraint("ck_paper_receipt_line_sheets_valid", "paper_receipt_lines", type_="check")
    op.drop_constraint("ck_paper_receipt_line_received_valid", "paper_receipt_lines", type_="check")
    op.create_check_constraint("ck_paper_receipt_line_received_qty_pos", "paper_receipt_lines", "received_quantity > 0")
    for col in ("damaged_sheets", "accepted_sheets", "received_sheets", "challan_sheets"):
        op.drop_column("paper_receipt_lines", col)

    op.drop_constraint("ck_paper_exactly_one_direction", "paper_stock_movements", type_="check")
    op.create_check_constraint(
        "ck_paper_exactly_one_quantity_direction",
        "paper_stock_movements",
        "((quantity_in > 0 AND quantity_out = 0) OR (quantity_out > 0 AND quantity_in = 0))",
    )
    op.drop_constraint("ck_paper_sheets_out_nonnegative", "paper_stock_movements", type_="check")
    op.drop_constraint("ck_paper_sheets_in_nonnegative", "paper_stock_movements", type_="check")
    op.drop_column("paper_stock_movements", "sheets_out")
    op.drop_column("paper_stock_movements", "sheets_in")

    op.drop_constraint("ck_paper_items_sheets_per_ream_positive", "paper_items", type_="check")
    op.drop_column("paper_items", "sheets_per_ream")

