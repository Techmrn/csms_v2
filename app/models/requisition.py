from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.item import Item
    from app.models.office import Office
    from app.models.store import Store
    from app.models.user import User


class CentralStoreRequisition(TimestampMixin, Base):
    __tablename__ = "central_store_requisitions"
    __table_args__ = (
        CheckConstraint(
            "status in ('SUBMITTED','BRANCH_APPROVED','CENTRAL_APPROVED','READY_FOR_TRANSFER','DISPATCHED','RECEIVED','DISCREPANCY','CLOSED','REJECTED','CANCELLED')",
            name="status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requisition_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    requisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    requesting_office_id: Mapped[int] = mapped_column(
        ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False
    )
    requesting_store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="SUBMITTED")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    branch_approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    branch_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    central_approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    central_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["CentralStoreRequisitionLine"]] = relationship(
        back_populates="requisition", cascade="all, delete-orphan", lazy="selectin"
    )


class CentralStoreRequisitionLine(Base):
    __tablename__ = "central_store_requisition_lines"
    __table_args__ = (
        UniqueConstraint("requisition_id", "item_id", name="uq_csr_lines_requisition_item"),
        CheckConstraint("requested_quantity > 0", name="requested_quantity_positive"),
        CheckConstraint(
            "approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity)",
            name="approved_quantity_valid",
        ),
        CheckConstraint("dispatched_quantity >= 0", name="dispatched_quantity_nonnegative"),
        CheckConstraint("received_quantity >= 0", name="received_quantity_nonnegative"),
        CheckConstraint(
            "dispatched_quantity <= coalesce(approved_quantity, 0)",
            name="dispatched_quantity_not_greater_than_approved",
        ),
        CheckConstraint(
            "received_quantity <= dispatched_quantity",
            name="received_quantity_not_greater_than_dispatched",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requisition_id: Mapped[int] = mapped_column(
        ForeignKey("central_store_requisitions.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    dispatched_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    received_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3), nullable=False, default=Decimal("0")
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    requisition: Mapped[CentralStoreRequisition] = relationship(back_populates="lines")
    item: Mapped["Item"] = relationship()
