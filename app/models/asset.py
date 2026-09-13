from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.store import Store
    from app.models.office import Office
    from app.models.section import Section
    from app.models.user import User
    from app.models.financial_year import FinancialYear
    from app.models.receipt import ReceiptLine


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        CheckConstraint(
            "status in ('IN_STOCK','ASSIGNED','UNDER_REPAIR','UNSERVICEABLE','DISPOSED','LOST')",
            name="ck_assets_status_valid",
        ),
        Index("ix_assets_item_id", "item_id"),
        Index("ix_assets_current_store_id", "current_store_id"),
        Index("ix_assets_current_office_id", "current_office_id"),
        Index("ix_assets_current_section_id", "current_section_id"),
        Index("ix_assets_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    serial_no: Mapped[str | None] = mapped_column(String(150), nullable=True)

    current_store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True)
    current_office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True)
    current_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="IN_STOCK")
    acquisition_financial_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=True
    )

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped["Item"] = relationship()
    detail: Mapped["AssetDetail | None"] = relationship(
        back_populates="asset", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    movements: Mapped[list["AssetMovement"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )
    repairs: Mapped[list["AssetRepair"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )


class AssetDetail(TimestampMixin, Base):
    __tablename__ = "asset_details"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    make: Mapped[str | None] = mapped_column(String(150), nullable=True)
    model: Mapped[str | None] = mapped_column(String(150), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purchase_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    warranty_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    technical_specifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="detail")


class AssetMovement(TimestampMixin, Base):
    __tablename__ = "asset_movements"
    __table_args__ = (
        CheckConstraint(
            "movement_type in ('RECEIPT','ASSIGNMENT','TRANSFER','RETURN','REPAIR','UNSERVICEABLE','DISPOSAL','LOST','LOCATION_CHANGE')",
            name="ck_asset_movements_type_valid",
        ),
        Index("ix_asset_movements_asset_date", "asset_id", "movement_date"),
        Index("ix_asset_movements_reference", "reference_type", "reference_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)

    from_store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True)
    to_store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True)
    from_office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True)
    from_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True)
    to_office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True)
    to_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True)

    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reference_document: Mapped[str | None] = mapped_column(String(100), nullable=True)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    asset: Mapped[Asset] = relationship(back_populates="movements")


class ReceiptLineAsset(TimestampMixin, Base):
    __tablename__ = "receipt_line_assets"
    __table_args__ = (
        Index("ix_receipt_line_assets_asset_id", "asset_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    receipt_line_id: Mapped[int] = mapped_column(
        ForeignKey("receipt_lines.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )

    receipt_line: Mapped["ReceiptLine"] = relationship()
    asset: Mapped[Asset] = relationship()

class AssetRepair(TimestampMixin, Base):
    __tablename__ = "asset_repairs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    
    # Snapshot of the asset's state prior to repair
    previous_store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True)
    previous_office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True)
    previous_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True)
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)

    sent_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNDER_REPAIR")
    
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    returned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="repairs")
