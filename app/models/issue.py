from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.indent import Indent
    from app.models.item import Item
    from app.models.store import Store
    from app.models.unit import Unit
    from app.models.asset import Asset


class Issue(TimestampMixin, Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    issue_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    indent_id: Mapped[int] = mapped_column(
        ForeignKey("indents.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    source_store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    destination_office_id: Mapped[int] = mapped_column(
        ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False
    )
    destination_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True
    )
    destination_type: Mapped[str] = mapped_column(String(20), nullable=False, default="SECTION")
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="FINALIZED")
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    lines: Mapped[list["IssueLine"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", lazy="selectin"
    )


class IssueLine(Base):
    __tablename__ = "issue_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    remarks: Mapped[str | None] = mapped_column(nullable=True)

    issue: Mapped[Issue] = relationship(back_populates="lines")
    item: Mapped["Item"] = relationship()
    unit: Mapped["Unit"] = relationship()
    
    asset_links: Mapped[list["IssueLineAsset"]] = relationship(
        back_populates="issue_line", cascade="all, delete-orphan", lazy="selectin"
    )

class IssueLineAsset(TimestampMixin, Base):
    __tablename__ = "issue_line_assets"
    __table_args__ = (
        Index("ix_issue_line_assets_asset_id", "asset_id"),
        UniqueConstraint("issue_line_id", "asset_id", name="uq_issue_line_assets_issue_line_asset"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    issue_line_id: Mapped[int] = mapped_column(
        ForeignKey("issue_lines.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )

    issue_line: Mapped[IssueLine] = relationship(back_populates="asset_links")
    asset: Mapped["Asset"] = relationship()
