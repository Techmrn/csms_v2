"""add manual indent and issue workflow

Revision ID: 0003_indent_issue
Revises: 0002_stock_core
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_indent_issue"
down_revision = "0002_stock_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS indent_no_seq START WITH 1")
    op.execute("CREATE SEQUENCE IF NOT EXISTS issue_no_seq START WITH 1")

    op.create_table(
        "indents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("indent_no", sa.String(50), nullable=False, unique=True),
        sa.Column("indent_date", sa.Date(), nullable=False),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("office_id", sa.BigInteger(), nullable=False),
        sa.Column("section_id", sa.BigInteger(), nullable=True),
        sa.Column("request_source", sa.String(20), nullable=False),
        sa.Column("request_type", sa.String(20), nullable=True),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("request_source in ('PHYSICAL','ONLINE')", name="ck_indents_request_source_valid"),
    )
    op.create_index("ix_indents_store_status", "indents", ["store_id", "status"])
    op.create_index("ix_indents_fy_date", "indents", ["financial_year_id", "indent_date"])

    op.create_table(
        "indent_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("indent_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("issued_quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["indent_id"], ["indents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("indent_id", "item_id", name="uq_indent_lines_indent_item"),
        sa.CheckConstraint("requested_quantity > 0", name="ck_indent_lines_requested_quantity_positive"),
        sa.CheckConstraint("issued_quantity is null or issued_quantity >= 0", name="ck_indent_lines_issued_quantity_nonnegative"),
        sa.CheckConstraint("issued_quantity is null or issued_quantity <= requested_quantity", name="ck_indent_lines_issued_quantity_not_greater_than_requested"),
    )
    op.create_index("ix_indent_lines_item", "indent_lines", ["item_id"])

    op.create_table(
        "issues",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("issue_no", sa.String(50), nullable=False, unique=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("financial_year_id", sa.BigInteger(), nullable=False),
        sa.Column("indent_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("source_store_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_office_id", sa.BigInteger(), nullable=False),
        sa.Column("destination_section_id", sa.BigInteger(), nullable=True),
        sa.Column("destination_type", sa.String(20), nullable=False),
        sa.Column("reference_no", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_by", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posting_group_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["financial_year_id"], ["financial_years.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["indent_id"], ["indents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_office_id"], ["offices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_section_id"], ["sections.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_issues_store_date", "issues", ["source_store_id", "issue_date"])
    op.create_index("ix_issues_destination", "issues", ["destination_office_id", "destination_section_id"])

    op.create_table(
        "issue_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("quantity >= 0", name="ck_issue_lines_quantity_nonnegative"),
    )
    op.create_index("ix_issue_lines_item", "issue_lines", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_issue_lines_item", table_name="issue_lines")
    op.drop_table("issue_lines")
    op.drop_index("ix_issues_destination", table_name="issues")
    op.drop_index("ix_issues_store_date", table_name="issues")
    op.drop_table("issues")
    op.drop_index("ix_indent_lines_item", table_name="indent_lines")
    op.drop_table("indent_lines")
    op.drop_index("ix_indents_fy_date", table_name="indents")
    op.drop_index("ix_indents_store_status", table_name="indents")
    op.drop_table("indents")
    op.execute("DROP SEQUENCE IF EXISTS issue_no_seq")
    op.execute("DROP SEQUENCE IF EXISTS indent_no_seq")
