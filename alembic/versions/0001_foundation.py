"""create CSMS V2 foundation tables

Revision ID: 0001_foundation
Revises:
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("office_type", sa.String(30), nullable=False),
        sa.Column("parent_office_id", sa.BigInteger(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("office_type in ('DIRECTORATE','BRANCH','OTHER')", name="ck_offices_office_type_valid"),
        sa.ForeignKeyConstraint(["parent_office_id"], ["offices.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "sections",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("office_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("office_id", "code", name="uq_sections_office_code"),
    )
    op.create_table(
        "stores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("office_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("store_type", sa.String(30), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("store_type in ('CENTRAL','BRANCH','OTHER')", name="ck_stores_store_type_valid"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # users must be created before relation tables
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("designation", sa.String(200), nullable=True),
        sa.Column("office_id", sa.BigInteger(), nullable=True),
        sa.Column("section_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("mobile", sa.String(30), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "user_stores",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("store_id", sa.BigInteger(), sa.ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.BigInteger(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "financial_years",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("year_name", sa.String(20), nullable=False, unique=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_date < end_date", name="ck_financial_years_financial_year_dates_valid"),
    )
    op.create_index("uq_current_financial_year", "financial_years", ["is_current"], unique=True, postgresql_where=sa.text("is_current = true"))
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type in ('CONSUMABLE','ASSET')", name="ck_categories_category_type_valid"),
    )
    op.create_table(
        "units",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("decimal_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "inventory_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("reorder_level", sa.Numeric(18, 3), nullable=True),
        sa.Column("reorder_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("maximum_stock_level", sa.Numeric(18, 3), nullable=True),
        sa.Column("low_stock_level", sa.Numeric(18, 3), nullable=True),
        sa.Column("issue_method", sa.String(20), nullable=True),
        sa.Column("batch_tracking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expiry_tracking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expiry_alert_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("store_id", "item_id", name="uq_inventory_policy_store_item"),
        sa.CheckConstraint("reorder_level is null or reorder_level >= 0", name="ck_inventory_policies_reorder_level_valid"),
        sa.CheckConstraint("reorder_quantity is null or reorder_quantity > 0", name="ck_inventory_policies_reorder_quantity_valid"),
        sa.CheckConstraint("maximum_stock_level is null or maximum_stock_level >= 0", name="ck_inventory_policies_maximum_stock_level_valid"),
        sa.CheckConstraint("low_stock_level is null or low_stock_level >= 0", name="ck_inventory_policies_low_stock_level_valid"),
        sa.CheckConstraint("issue_method is null or issue_method in ('NONE','FIFO','LIFO','FEFO')", name="ck_inventory_policies_issue_method_valid"),
        sa.CheckConstraint("expiry_alert_days is null or expiry_alert_days >= 0", name="ck_inventory_policies_expiry_alert_days_valid"),
    )
    op.create_index("ix_stores_office_id", "stores", ["office_id"])
    op.create_index("ix_sections_office_id", "sections", ["office_id"])
    op.create_index("ix_users_office_id", "users", ["office_id"])
    op.create_index("ix_users_section_id", "users", ["section_id"])
    op.create_index("ix_items_category_id", "items", ["category_id"])
    op.create_index("ix_items_unit_id", "items", ["unit_id"])


def downgrade() -> None:
    for table in [
        "inventory_policies", "items", "units", "categories", "financial_years",
        "role_permissions", "user_stores", "user_roles", "users", "permissions",
        "roles", "stores", "sections", "offices",
    ]:
        op.drop_table(table)
