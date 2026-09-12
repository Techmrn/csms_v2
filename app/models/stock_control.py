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
    from app.models.item import Item
    from app.models.store import Store
    from app.models.user import User


class StockVerification(TimestampMixin, Base):
    __tablename__ = "stock_verifications"
    __table_args__ = (
        CheckConstraint(
            "status in ('OPEN','COUNTED','AUTHORIZED','CLOSED','CANCELLED')",
            name="ck_stock_verifications_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    verification_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    counted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    authorized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["StockVerificationLine"]] = relationship(
        back_populates="verification", cascade="all, delete-orphan", lazy="selectin"
    )


class StockVerificationLine(Base):
    __tablename__ = "stock_verification_lines"
    __table_args__ = (
        UniqueConstraint("verification_id", "item_id", name="uq_stock_verification_lines_verification_item"),
        CheckConstraint("system_quantity >= 0", name="ck_stock_verification_system_nonnegative"),
        CheckConstraint("physical_quantity >= 0", name="ck_stock_verification_physical_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("stock_verifications.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    system_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    physical_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    variance_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    verification: Mapped[StockVerification] = relationship(back_populates="lines")


class Adjustment(TimestampMixin, Base):
    __tablename__ = "adjustments"
    __table_args__ = (
        UniqueConstraint("verification_id", "adjustment_type", name="uq_adjustments_verification_type"),
        CheckConstraint(
            "status in ('OPEN','AUTHORIZED','POSTED','CANCELLED')",
            name="ck_adjustments_status_valid",
        ),
        CheckConstraint(
            "adjustment_type in ('ADJUSTMENT_IN','ADJUSTMENT_OUT')",
            name="ck_adjustments_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    adjustment_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    adjustment_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("stock_verifications.id", ondelete="RESTRICT"), nullable=False
    )
    adjustment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    authorized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    lines: Mapped[list["AdjustmentLine"]] = relationship(
        back_populates="adjustment", cascade="all, delete-orphan", lazy="selectin"
    )
    verification: Mapped[StockVerification] = relationship()


class AdjustmentLine(Base):
    __tablename__ = "adjustment_lines"
    __table_args__ = (
        UniqueConstraint("adjustment_id", "item_id", name="uq_adjustment_lines_adjustment_item"),
        CheckConstraint("quantity > 0", name="ck_adjustment_line_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    adjustment_id: Mapped[int] = mapped_column(
        ForeignKey("adjustments.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    adjustment: Mapped[Adjustment] = relationship(back_populates="lines")


class UnserviceableMaterial(TimestampMixin, Base):
    __tablename__ = "unserviceable_materials"
    __table_args__ = (
        CheckConstraint(
            "status in ('REPORTED','VERIFIED','AUTHORIZED','POSTED','CANCELLED')",
            name="ck_unserviceable_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reference_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="REPORTED")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    authorized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    lines: Mapped[list["UnserviceableLine"]] = relationship(
        back_populates="unserviceable", cascade="all, delete-orphan", lazy="selectin"
    )


class UnserviceableLine(Base):
    __tablename__ = "unserviceable_lines"
    __table_args__ = (
        UniqueConstraint("unserviceable_id", "item_id", name="uq_unserviceable_lines_material_item"),
        CheckConstraint("quantity > 0", name="ck_unserviceable_line_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    unserviceable_id: Mapped[int] = mapped_column(
        ForeignKey("unserviceable_materials.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    unserviceable: Mapped[UnserviceableMaterial] = relationship(back_populates="lines")
