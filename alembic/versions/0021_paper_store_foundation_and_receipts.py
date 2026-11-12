"""Paper store foundation, authoritative paper ledger, and stationery receipts.

Revision ID: 0021_paper_store_foundation_and_receipts
Revises: 0020_redefine_inter_store_transfer
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0021_paper_store_foundation_and_receipts"
down_revision = "0020_redefine_inter_store_transfer"
branch_labels = None
depends_on = None

PAPER_PERMISSIONS = [
    ("PAPER_VIEW", "View paper warehouse stock, transactions, and registers", "PAPER", "VIEW"),
    ("PAPER_RECEIPT_CREATE", "Create manual paper receipt from Stationery Department", "PAPER", "RECEIPT_CREATE"),
    ("PAPER_RECEIPT_POST", "Verify and post paper receipt to warehouse stock", "PAPER", "RECEIPT_POST"),
    ("PAPER_ISSUE", "Issue paper to press sections", "PAPER", "ISSUE"),
    ("PAPER_TRANSFER_CREATE", "Create inter-press paper transfer request", "PAPER", "TRANSFER_CREATE"),
    ("PAPER_TRANSFER_DIRECTIVE", "Initiate inter-press transfer directive", "PAPER", "TRANSFER_DIRECTIVE"),
    ("PAPER_TRANSFER_APPROVE", "Approve inter-press paper transfer", "PAPER", "TRANSFER_APPROVE"),
    ("PAPER_TRANSFER_DISPATCH", "Dispatch inter-press transfer", "PAPER", "TRANSFER_DISPATCH"),
    ("PAPER_TRANSFER_RECEIVE", "Receive inter-press transfer", "PAPER", "TRANSFER_RECEIVE"),
    ("PAPER_INDENT_CREATE", "Create section paper indent", "PAPER", "INDENT_CREATE"),
    ("PAPER_MASTER_MANAGE", "Manage paper items catalog", "PAPER", "MASTER_MANAGE"),
]


def upgrade() -> None:
    # 1. Allow 'PAPER_WAREHOUSE' as valid store_type on stores
    op.drop_constraint("ck_stores_store_type_valid", "stores", type_="check")
    op.create_check_constraint(
        "ck_stores_store_type_valid",
        "stores",
        "store_type in ('CENTRAL','BRANCH','PAPER_WAREHOUSE','OTHER')",
    )

    # 2. Create paper_items table
    op.create_table(
        "paper_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("paper_type", sa.String(100), nullable=False),
        sa.Column("form_type", sa.String(20), nullable=False),
        sa.Column("gsm", sa.Integer(), nullable=False),
        sa.Column("length_cm", sa.Numeric(10, 2), nullable=True),
        sa.Column("width_cm", sa.Numeric(10, 2), nullable=True),
        sa.Column("reel_width_cm", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("weight_per_ream_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("form_type in ('SHEET', 'REEL')", name="ck_paper_items_form_type_valid"),
        sa.CheckConstraint("gsm > 0", name="ck_paper_items_gsm_positive"),
        sa.UniqueConstraint("name", "gsm", "form_type", name="uq_paper_items_name_gsm_form"),
    )

    # 3. Create paper_stock_accounts table (Concurrency Anchor)
    op.create_table(
        "paper_stock_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("store_id", "financial_year_id", "paper_item_id", name="uq_paper_stock_accounts_store_fy_item"),
    )

    # 4. Create paper_stock_movements table (Authoritative Ledger)
    op.create_table(
        "paper_stock_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("movement_type", sa.String(40), nullable=False),
        sa.Column("quantity_in", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("quantity_out", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("weight_kg_in", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("weight_kg_out", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("reference_type", sa.String(40), nullable=False),
        sa.Column("reference_id", sa.BigInteger(), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("posting_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity_in >= 0", name="ck_paper_quantity_in_nonnegative"),
        sa.CheckConstraint("quantity_out >= 0", name="ck_paper_quantity_out_nonnegative"),
        sa.CheckConstraint("weight_kg_in >= 0", name="ck_paper_weight_in_nonnegative"),
        sa.CheckConstraint("weight_kg_out >= 0", name="ck_paper_weight_out_nonnegative"),
        sa.CheckConstraint(
            "((quantity_in > 0 AND quantity_out = 0) OR (quantity_out > 0 AND quantity_in = 0))",
            name="ck_paper_exactly_one_quantity_direction",
        ),
        sa.UniqueConstraint("reference_type", "reference_id", "paper_item_id", "movement_type", name="uq_paper_stock_movements_reference_item_type"),
    )

    # 5. Create paper_receipts table
    op.create_table(
        "paper_receipts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("receipt_no", sa.String(50), nullable=False, unique=True),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.Integer(), sa.ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_depot", sa.String(255), nullable=False),
        sa.Column("allotment_no", sa.String(100), nullable=True),
        sa.Column("allotment_date", sa.Date(), nullable=True),
        sa.Column("challan_no", sa.String(100), nullable=True),
        sa.Column("challan_date", sa.Date(), nullable=True),
        sa.Column("vehicle_no", sa.String(50), nullable=True),
        sa.Column("carrier_name", sa.String(100), nullable=True),
        sa.Column("lorry_receipt_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="POSTED"),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('DRAFT', 'POSTED', 'CANCELLED')", name="ck_paper_receipt_status_valid"),
    )

    # 6. Create paper_receipt_lines table
    op.create_table(
        "paper_receipt_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("paper_receipt_id", sa.BigInteger(), sa.ForeignKey("paper_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paper_item_id", sa.Integer(), sa.ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("challan_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("damaged_quantity", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("weight_kg", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("reel_count", sa.Integer(), nullable=True),
        sa.Column("reel_numbers", sa.String(255), nullable=True),
        sa.Column("remarks", sa.String(255), nullable=True),
        sa.CheckConstraint("challan_quantity >= 0", name="ck_paper_receipt_line_challan_qty_nonneg"),
        sa.CheckConstraint("received_quantity > 0", name="ck_paper_receipt_line_received_qty_pos"),
        sa.CheckConstraint("accepted_quantity >= 0", name="ck_paper_receipt_line_accepted_qty_nonneg"),
        sa.CheckConstraint("damaged_quantity >= 0", name="ck_paper_receipt_line_damaged_qty_nonneg"),
        sa.CheckConstraint("accepted_quantity + damaged_quantity <= received_quantity", name="ck_paper_receipt_line_accepted_damaged_lte_received"),
        sa.CheckConstraint("weight_kg >= 0", name="ck_paper_receipt_line_weight_kg_nonneg"),
    )

    # 7. Seed permissions and role assignments
    conn = op.get_bind()
    for code, name, module, action in PAPER_PERMISSIONS:
        conn.execute(
            sa.text(
                """INSERT INTO permissions (code, name, module, action, is_active, created_at, updated_at)
                   VALUES (:code, :name, :module, :action, TRUE, NOW(), NOW())
                   ON CONFLICT (code) DO NOTHING"""
            ),
            dict(code=code, name=name, module=module, action=action),
        )

    # System Admin permissions
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'SYSTEM_ADMIN' AND p.code IN ('PAPER_VIEW', 'PAPER_MASTER_MANAGE')
               ON CONFLICT DO NOTHING"""
        )
    )

    # Directorate permissions (Director & Dy Supdt)
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code IN ('DIRECTOR', 'DEPUTY_SUPDT_STORES')
                 AND p.code IN ('PAPER_VIEW', 'PAPER_TRANSFER_DIRECTIVE')
               ON CONFLICT DO NOTHING"""
        )
    )

    # Branch Head permissions
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'BRANCH_HEAD'
                 AND p.code IN ('PAPER_VIEW', 'PAPER_TRANSFER_APPROVE')
               ON CONFLICT DO NOTHING"""
        )
    )

    # Branch Storekeeper permissions
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'BRANCH_STOREKEEPER'
                 AND p.code IN (
                     'PAPER_VIEW', 'PAPER_RECEIPT_CREATE', 'PAPER_RECEIPT_POST',
                     'PAPER_ISSUE', 'PAPER_TRANSFER_CREATE', 'PAPER_TRANSFER_DISPATCH',
                     'PAPER_TRANSFER_RECEIVE'
                 )
               ON CONFLICT DO NOTHING"""
        )
    )

    # Section User permissions
    conn.execute(
        sa.text(
            """INSERT INTO role_permissions (role_id, permission_id)
               SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
               WHERE r.code = 'SECTION_USER'
                 AND p.code IN ('PAPER_VIEW', 'PAPER_INDENT_CREATE')
               ON CONFLICT DO NOTHING"""
        )
    )

    # 8. Seed Press Paper Warehouse and link to existing press office
    press_office = conn.execute(
        sa.text("SELECT id FROM offices WHERE code = 'PRESS' LIMIT 1")
    ).fetchone()

    if press_office:
        press_office_id = press_office[0]
        # Insert Paper Warehouse store
        conn.execute(
            sa.text(
                """INSERT INTO stores (office_id, code, name, store_type, is_primary, remarks, is_active, created_at, updated_at)
                   VALUES (:office_id, 'PRESS-PAPER-WH', 'Central Press Paper Warehouse', 'PAPER_WAREHOUSE', FALSE, 'Press Paper Warehouse', TRUE, NOW(), NOW())
                   ON CONFLICT (code) DO NOTHING"""
            ),
            dict(office_id=press_office_id),
        )

        # Assign storekeeper user of press office to the paper warehouse as well
        paper_store = conn.execute(
            sa.text("SELECT id FROM stores WHERE code = 'PRESS-PAPER-WH' LIMIT 1")
        ).fetchone()

        if paper_store:
            paper_store_id = paper_store[0]
            # Find branch storekeeper in press
            storekeepers = conn.execute(
                sa.text(
                    """SELECT u.id FROM users u
                       JOIN user_roles ur ON ur.user_id = u.id
                       JOIN roles r ON r.id = ur.role_id
                       WHERE r.code = 'BRANCH_STOREKEEPER' AND u.office_id = :office_id"""
                ),
                dict(office_id=press_office_id),
            ).fetchall()

            for sk in storekeepers:
                conn.execute(
                    sa.text(
                        """INSERT INTO user_stores (user_id, store_id, is_primary)
                           VALUES (:user_id, :store_id, FALSE)
                           ON CONFLICT DO NOTHING"""
                    ),
                    dict(user_id=sk[0], store_id=paper_store_id),
                )

    # 9. Seed sample paper items if units exist
    ream_unit = conn.execute(
        sa.text("SELECT id FROM units WHERE code = 'REAM' LIMIT 1")
    ).fetchone()
    kg_unit = conn.execute(
        sa.text("SELECT id FROM units WHERE code = 'KG' LIMIT 1")
    ).fetchone()

    if ream_unit and kg_unit:
        ream_id = ream_unit[0]
        kg_id = kg_unit[0]

        paper_seed_items = [
            ("PPR-MAP-70-RA1", "White Printing Maplitho 70 GSM 58.5 x 91 cm", "Maplitho", "SHEET", 70, 58.5, 91.0, None, ream_id, 18.632),
            ("PPR-MAP-80-RA1", "White Printing Maplitho 80 GSM 58.5 x 91 cm", "Maplitho", "SHEET", 80, 58.5, 91.0, None, ream_id, 21.294),
            ("PPR-CW-60-REEL84", "Creamwove 60 GSM 84 cm Reel", "Creamwove", "REEL", 60, None, None, 84.0, kg_id, None),
            ("PPR-ART-130-RA1", "Gloss Art Paper 130 GSM 58.5 x 91 cm", "Art Paper", "SHEET", 130, 58.5, 91.0, None, ream_id, 34.603),
            ("PPR-KRAFT-120-DEM", "Kraft Paper 120 GSM 43 x 69 cm", "Kraft", "SHEET", 120, 43.0, 69.0, None, ream_id, 17.802),
        ]

        for code, name, ptype, ftype, gsm, l_cm, w_cm, rw_cm, uid, w_ream in paper_seed_items:
            conn.execute(
                sa.text(
                    """INSERT INTO paper_items (code, name, paper_type, form_type, gsm, length_cm, width_cm, reel_width_cm, unit_id, weight_per_ream_kg, is_active, created_at, updated_at)
                       VALUES (:code, :name, :ptype, :ftype, :gsm, :l_cm, :w_cm, :rw_cm, :uid, :w_ream, TRUE, NOW(), NOW())
                       ON CONFLICT (code) DO NOTHING"""
                ),
                dict(code=code, name=name, ptype=ptype, ftype=ftype, gsm=gsm, l_cm=l_cm, w_cm=w_cm, rw_cm=rw_cm, uid=uid, w_ream=w_ream),
            )


def downgrade() -> None:
    op.drop_table("paper_receipt_lines")
    op.drop_table("paper_receipts")
    op.drop_table("paper_stock_movements")
    op.drop_table("paper_stock_accounts")
    op.drop_table("paper_items")

    op.drop_constraint("ck_stores_store_type_valid", "stores", type_="check")
    op.create_check_constraint(
        "ck_stores_store_type_valid",
        "stores",
        "store_type in ('CENTRAL','BRANCH','OTHER')",
    )

