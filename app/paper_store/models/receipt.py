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
    from app.models.store import Store
    from app.models.unit import Unit
    from app.models.user import User
    from app.paper_store.models.item import PaperItem


class PaperReceipt(TimestampMixin, Base):
    __tablename__ = "paper_receipts"
    __table_args__ = (
        CheckConstraint(
            "status in ('DRAFT', 'POSTED', 'CANCELLED')",
            name="ck_paper_receipt_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    source_depot: Mapped[str] = mapped_column(String(255), nullable=False)
    allotment_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    allotment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    challan_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    challan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    vehicle_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lorry_receipt_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="POSTED")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    lines: Mapped[list["PaperReceiptLine"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )
    store: Mapped["Store"] = relationship(lazy="selectin")
    financial_year: Mapped["FinancialYear"] = relationship(lazy="selectin")
    poster: Mapped["User | None"] = relationship(foreign_keys=[posted_by], lazy="selectin")


class PaperReceiptLine(Base):
    __tablename__ = "paper_receipt_lines"
    __table_args__ = (
        CheckConstraint("challan_quantity >= 0", name="ck_paper_receipt_line_challan_qty_nonneg"),
        CheckConstraint("accepted_quantity >= 0", name="ck_paper_receipt_line_accepted_qty_nonneg"),
        CheckConstraint("damaged_quantity >= 0", name="ck_paper_receipt_line_damaged_qty_nonneg"),
        CheckConstraint(
            "accepted_quantity + damaged_quantity <= received_quantity",
            name="ck_paper_receipt_line_accepted_damaged_lte_received",
        ),
        CheckConstraint("weight_kg >= 0", name="ck_paper_receipt_line_weight_kg_nonneg"),
        CheckConstraint(
            "received_sheets > 0 OR weight_kg > 0 OR received_quantity > 0",
            name="ck_paper_receipt_line_received_valid",
        ),
        CheckConstraint(
            "challan_sheets >= 0 AND received_sheets >= 0 AND accepted_sheets >= 0 "
            "AND damaged_sheets >= 0 AND (accepted_sheets + damaged_sheets <= received_sheets)",
            name="ck_paper_receipt_line_sheets_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paper_receipt_id: Mapped[int] = mapped_column(
        ForeignKey("paper_receipts.id", ondelete="CASCADE"), nullable=False
    )
    paper_item_id: Mapped[int] = mapped_column(
        ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    challan_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    accepted_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    damaged_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    challan_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    received_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    accepted_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    damaged_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    reel_count: Mapped[int | None] = mapped_column(nullable=True)
    reel_numbers: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    receipt: Mapped["PaperReceipt"] = relationship(back_populates="lines")
    paper_item: Mapped["PaperItem"] = relationship(lazy="selectin")
    unit: Mapped["Unit"] = relationship(lazy="selectin")

