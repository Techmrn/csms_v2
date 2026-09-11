from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.item import Item
    from app.models.store import Store
    from app.models.unit import Unit


class Receipt(TimestampMixin, Base):
    __tablename__ = "receipts"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="EXTERNAL")
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    challan_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
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

    lines: Mapped[list["ReceiptLine"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"
    __table_args__ = (
        CheckConstraint("received_quantity > 0", name="received_quantity_positive"),
        CheckConstraint("accepted_quantity >= 0", name="accepted_quantity_nonnegative"),
        CheckConstraint("rejected_quantity >= 0", name="rejected_quantity_nonnegative"),
        CheckConstraint(
            "accepted_quantity + rejected_quantity <= received_quantity",
            name="accepted_rejected_not_greater_than_received",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    accepted_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    rejected_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    receipt: Mapped[Receipt] = relationship(back_populates="lines")
    item: Mapped["Item"] = relationship()
    unit: Mapped["Unit"] = relationship()
