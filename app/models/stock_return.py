from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.issue import Issue, IssueLine
    from app.models.item import Item
    from app.models.office import Office
    from app.models.section import Section
    from app.models.store import Store
    from app.models.unit import Unit


class StockReturn(TimestampMixin, Base):
    __tablename__ = "stock_returns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    return_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    original_issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="RESTRICT"), nullable=False
    )
    returning_office_id: Mapped[int | None] = mapped_column(
        ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True
    )
    returning_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    verified_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    lines: Mapped[list["StockReturnLine"]] = relationship(
        back_populates="stock_return", cascade="all, delete-orphan", lazy="selectin"
    )


class StockReturnLine(Base):
    __tablename__ = "stock_return_lines"
    __table_args__ = (
        UniqueConstraint(
            "return_id", "original_issue_line_id", name="uq_stock_return_lines_return_issue_line"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    return_id: Mapped[int] = mapped_column(
        ForeignKey("stock_returns.id", ondelete="CASCADE"), nullable=False
    )
    original_issue_line_id: Mapped[int] = mapped_column(
        ForeignKey("issue_lines.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    stock_return: Mapped[StockReturn] = relationship(back_populates="lines")
    original_issue_line: Mapped["IssueLine"] = relationship()
    item: Mapped["Item"] = relationship()
    unit: Mapped["Unit"] = relationship()
