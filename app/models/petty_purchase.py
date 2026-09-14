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
    from app.models.indent import Indent
    from app.models.item import Item
    from app.models.store import Store
    from app.models.unit import Unit


class PettyPurchase(TimestampMixin, Base):
    __tablename__ = "petty_purchases"
    __table_args__ = (
        CheckConstraint(
            "status in ('OPEN','VERIFIED','POSTED','CANCELLED')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    petty_purchase_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    # Required only when at least one line has immediate_issue_quantity > 0.
    indent_id: Mapped[int | None] = mapped_column(
        ForeignKey("indents.id", ondelete="RESTRICT"), nullable=True
    )
    # Destination is only used when an immediate issue is requested and no
    # pre-existing indent is supplied. The service creates the internal indent
    # atomically when the petty purchase is posted.
    issue_office_id: Mapped[int | None] = mapped_column(
        ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True
    )
    issue_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True
    )
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    lines: Mapped[list["PettyPurchaseLine"]] = relationship(
        back_populates="petty_purchase", cascade="all, delete-orphan", lazy="selectin"
    )
    indent: Mapped["Indent | None"] = relationship()


class PettyPurchaseLine(Base):
    __tablename__ = "petty_purchase_lines"
    __table_args__ = (
        UniqueConstraint("petty_purchase_id", "item_id", name="uq_petty_purchase_lines_purchase_item"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "immediate_issue_quantity >= 0 and immediate_issue_quantity <= quantity",
            name="immediate_issue_quantity_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    petty_purchase_id: Mapped[int] = mapped_column(
        ForeignKey("petty_purchases.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    # Retained snapshot for one-off/new items before later promotion/renaming.
    temporary_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temporary_specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    immediate_issue_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    petty_purchase: Mapped[PettyPurchase] = relationship(back_populates="lines")
    item: Mapped["Item"] = relationship()
    unit: Mapped["Unit"] = relationship()
