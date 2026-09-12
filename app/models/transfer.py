from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.item import Item
    from app.models.store import Store
    from app.models.user import User
    from app.models.requisition import CentralStoreRequisition


class StockTransfer(TimestampMixin, Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        CheckConstraint("source_store_id <> destination_store_id", name="source_destination_store_different"),
        CheckConstraint(
            "status in ('APPROVED','DISPATCHED','RECEIVED','DISCREPANCY','CLOSED','CANCELLED')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transfer_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    source_store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    destination_store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    requisition_id: Mapped[int] = mapped_column(
        ForeignKey("central_store_requisitions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="APPROVED")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    dispatched_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["StockTransferLine"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan", lazy="selectin"
    )


class StockTransferLine(Base):
    __tablename__ = "stock_transfer_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transfer_id: Mapped[int] = mapped_column(
        ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False
    )
    requisition_line_id: Mapped[int] = mapped_column(
        ForeignKey("central_store_requisition_lines.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    transfer: Mapped[StockTransfer] = relationship(back_populates="lines")
    item: Mapped["Item"] = relationship()


class TransferDiscrepancy(TimestampMixin, Base):
    __tablename__ = "transfer_discrepancies"
    __table_args__ = (
        CheckConstraint(
            "discrepancy_type in ('SHORT_RECEIPT','EXCESS_RECEIPT','DAMAGED','WRONG_ITEM','OTHER')",
            name="discrepancy_type_valid",
        ),
        CheckConstraint("discrepancy_quantity > 0", name="discrepancy_quantity_positive"),
        CheckConstraint(
            "status in ('OPEN','UNDER_REVIEW','RESOLVED','CLOSED')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transfer_id: Mapped[int] = mapped_column(
        ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False
    )
    transfer_line_id: Mapped[int] = mapped_column(
        ForeignKey("stock_transfer_lines.id", ondelete="CASCADE"), nullable=False
    )
    receive_date: Mapped[date] = mapped_column(Date, nullable=False)
    discrepancy_type: Mapped[str] = mapped_column(String(30), nullable=False)
    discrepancy_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
