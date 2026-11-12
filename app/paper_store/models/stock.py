from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.store import Store
    from app.models.unit import Unit
    from app.models.user import User
    from app.paper_store.models.item import PaperItem


class PaperStockAccount(TimestampMixin, Base):
    """Stable row used as the concurrency anchor for Paper Warehouse / FY / PaperItem stock."""

    __tablename__ = "paper_stock_accounts"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "financial_year_id", "paper_item_id",
            name="uq_paper_stock_accounts_store_fy_item",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    paper_item_id: Mapped[int] = mapped_column(ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False)


class PaperStockMovement(TimestampMixin, Base):
    __tablename__ = "paper_stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_in >= 0", name="ck_paper_quantity_in_nonnegative"),
        CheckConstraint("quantity_out >= 0", name="ck_paper_quantity_out_nonnegative"),
        CheckConstraint("sheets_in >= 0", name="ck_paper_sheets_in_nonnegative"),
        CheckConstraint("sheets_out >= 0", name="ck_paper_sheets_out_nonnegative"),
        CheckConstraint("weight_kg_in >= 0", name="ck_paper_weight_in_nonnegative"),
        CheckConstraint("weight_kg_out >= 0", name="ck_paper_weight_out_nonnegative"),
        CheckConstraint(
            "(((sheets_in > 0 OR weight_kg_in > 0) AND sheets_out = 0 AND weight_kg_out = 0) "
            "OR ((sheets_out > 0 OR weight_kg_out > 0) AND sheets_in = 0 AND weight_kg_in = 0))",
            name="ck_paper_exactly_one_direction",
        ),
        UniqueConstraint(
            "reference_type",
            "reference_id",
            "paper_item_id",
            "movement_type",
            name="uq_paper_stock_movements_reference_item_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    paper_item_id: Mapped[int] = mapped_column(ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity_in: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    quantity_out: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    sheets_in: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sheets_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    weight_kg_in: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    weight_kg_out: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    paper_item: Mapped["PaperItem"] = relationship(lazy="selectin")


class PaperOpeningStock(TimestampMixin, Base):
    __tablename__ = "paper_opening_stocks"
    __table_args__ = (
        CheckConstraint("opening_type in ('INITIAL', 'CARRY_FORWARD')", name="ck_paper_opening_type_valid"),
        CheckConstraint("status in ('OPEN', 'POSTED', 'CANCELLED')", name="ck_paper_opening_status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opening_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    opening_type: Mapped[str] = mapped_column(String(20), nullable=False, default="INITIAL")
    source_financial_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    store: Mapped["Store"] = relationship(lazy="selectin")
    financial_year: Mapped["FinancialYear"] = relationship(foreign_keys=[financial_year_id], lazy="selectin")
    source_financial_year: Mapped["FinancialYear | None"] = relationship(
        foreign_keys=[source_financial_year_id], lazy="selectin"
    )
    lines: Mapped[list["PaperOpeningStockLine"]] = relationship(
        back_populates="opening_stock", cascade="all, delete-orphan", lazy="selectin"
    )


class PaperOpeningStockLine(Base):
    __tablename__ = "paper_opening_stock_lines"
    __table_args__ = (
        UniqueConstraint("opening_stock_id", "paper_item_id", name="uq_paper_opening_line_opening_item"),
        CheckConstraint("total_sheets >= 0 AND weight_kg >= 0", name="ck_paper_opening_line_nonneg"),
        CheckConstraint("total_sheets > 0 OR weight_kg > 0", name="ck_paper_opening_line_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opening_stock_id: Mapped[int] = mapped_column(
        ForeignKey("paper_opening_stocks.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    paper_item_id: Mapped[int] = mapped_column(ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    total_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    reel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    opening_stock: Mapped[PaperOpeningStock] = relationship(back_populates="lines")
    paper_item: Mapped["PaperItem"] = relationship(lazy="selectin")
    unit: Mapped["Unit"] = relationship(lazy="selectin")
