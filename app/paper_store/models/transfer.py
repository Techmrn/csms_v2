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


class PaperTransfer(TimestampMixin, Base):
    __tablename__ = "paper_transfers"
    __table_args__ = (
        CheckConstraint(
            "source_store_id <> destination_store_id",
            name="ck_paper_transfer_src_dst_different",
        ),
        CheckConstraint(
            "transfer_mode in ('PULL', 'PUSH')",
            name="ck_paper_transfer_mode_valid",
        ),
        CheckConstraint(
            "status in ('SUBMITTED', 'DIRECTORATE_DIRECTIVE', 'BRANCH_APPROVED', 'DISPATCHED', 'RECEIVED', 'DISCREPANCY', 'CLOSED', 'REJECTED', 'CANCELLED')",
            name="ck_paper_transfer_status_valid",
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
    transfer_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="PULL")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="SUBMITTED")
    vehicle_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gate_pass_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    branch_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    branch_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    directorate_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    directorate_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dispatch_posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)
    receive_posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    source_store: Mapped["Store"] = relationship(foreign_keys=[source_store_id], lazy="selectin")
    destination_store: Mapped["Store"] = relationship(foreign_keys=[destination_store_id], lazy="selectin")
    financial_year: Mapped["FinancialYear"] = relationship(lazy="selectin")
    creator: Mapped["User"] = relationship(foreign_keys=[created_by], lazy="selectin")
    lines: Mapped[list["PaperTransferLine"]] = relationship(
        back_populates="transfer", cascade="all, delete-orphan", lazy="selectin"
    )


class PaperTransferLine(Base):
    __tablename__ = "paper_transfer_lines"
    __table_args__ = (
        CheckConstraint(
            "requested_sheets > 0 OR requested_weight_kg > 0 OR requested_quantity > 0",
            name="ck_paper_transfer_line_req_valid",
        ),
        CheckConstraint("dispatched_quantity >= 0", name="ck_paper_transfer_line_disp_qty_nonneg"),
        CheckConstraint("received_quantity >= 0", name="ck_paper_transfer_line_recv_qty_nonneg"),
        CheckConstraint("weight_kg >= 0", name="ck_paper_transfer_line_wt_nonneg"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transfer_id: Mapped[int] = mapped_column(
        ForeignKey("paper_transfers.id", ondelete="CASCADE"), nullable=False
    )
    paper_item_id: Mapped[int] = mapped_column(
        ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    dispatched_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    requested_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    approved_sheets: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    dispatched_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    received_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    requested_weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    dispatched_weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    received_weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    transfer: Mapped[PaperTransfer] = relationship(back_populates="lines")
    paper_item: Mapped["PaperItem"] = relationship(lazy="selectin")
    unit: Mapped["Unit"] = relationship(lazy="selectin")

