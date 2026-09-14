from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.item import Item
    from app.models.store import Store


class StockAccount(TimestampMixin, Base):
    """Stable row used as the concurrency anchor for Store/FY/Item stock."""

    __tablename__ = "stock_accounts"
    __table_args__ = (
        UniqueConstraint("store_id", "financial_year_id", "item_id", name="uq_stock_accounts_store_fy_item"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)


class StockMovement(TimestampMixin, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_in >= 0", name="quantity_in_nonnegative"),
        CheckConstraint("quantity_out >= 0", name="quantity_out_nonnegative"),
        CheckConstraint(
            "((quantity_in > 0 AND quantity_out = 0) OR (quantity_out > 0 AND quantity_in = 0))",
            name="exactly_one_direction",
        ),
        UniqueConstraint(
            "reference_type",
            "reference_id",
            "item_id",
            "movement_type",
            name="uq_stock_movements_reference_item_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    stock_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_batches.id", ondelete="RESTRICT"), nullable=True
    )
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_in: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    quantity_out: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class OpeningStock(TimestampMixin, Base):
    __tablename__ = "opening_stocks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opening_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    opening_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    remarks: Mapped[str | None] = mapped_column(nullable=True)
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

    lines: Mapped[list["OpeningStockLine"]] = relationship(
        back_populates="opening_stock", cascade="all, delete-orphan", lazy="selectin"
    )


class OpeningStockLine(Base):
    __tablename__ = "opening_stock_lines"
    __table_args__ = (
        UniqueConstraint("opening_stock_id", "item_id", name="uq_opening_stock_lines_opening_item"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opening_stock_id: Mapped[int] = mapped_column(
        ForeignKey("opening_stocks.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    asset_details: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    # Existing databases may contain historical duplicate opening lines created
    # before the one-opening-per-item rule was introduced. Those rows are kept
    # intact for audit/stock history and excluded from the new unique index.
    legacy_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"))

    opening_stock: Mapped[OpeningStock] = relationship(back_populates="lines")
