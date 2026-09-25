from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.financial_year import FinancialYear
    from app.models.item import Item
    from app.models.office import Office
    from app.models.section import Section
    from app.models.store import Store
    from app.models.user import User


class Indent(TimestampMixin, Base):
    __tablename__ = "indents"
    __table_args__ = (
        CheckConstraint(
            "request_source in ('PHYSICAL', 'ONLINE')",
            name="request_source_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    indent_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    indent_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    office_id: Mapped[int] = mapped_column(
        ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True
    )
    request_source: Mapped[str] = mapped_column(String(20), nullable=False, default="PHYSICAL")
    request_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RECORDED")
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    lines: Mapped[list["IndentLine"]] = relationship(
        back_populates="indent", cascade="all, delete-orphan", lazy="selectin"
    )
    store: Mapped["Store"] = relationship(lazy="selectin")
    office: Mapped["Office"] = relationship(lazy="selectin")
    section: Mapped["Section | None"] = relationship(lazy="selectin")
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by], lazy="selectin")


class IndentLine(Base):
    __tablename__ = "indent_lines"
    __table_args__ = (
        UniqueConstraint("indent_id", "item_id", name="uq_indent_lines_indent_item"),
        CheckConstraint("requested_quantity > 0", name="requested_quantity_positive"),
        CheckConstraint(
            "approved_quantity is null or (approved_quantity >= 0 and approved_quantity <= requested_quantity)",
            name="approved_quantity_valid",
        ),
        CheckConstraint(
            "issued_quantity is null or issued_quantity >= 0",
            name="issued_quantity_nonnegative",
        ),
        CheckConstraint(
            "issued_quantity is null or issued_quantity <= requested_quantity",
            name="issued_quantity_not_greater_than_requested",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    indent_id: Mapped[int] = mapped_column(
        ForeignKey("indents.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    issued_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)

    indent: Mapped[Indent] = relationship(back_populates="lines")
    item: Mapped["Item"] = relationship(lazy="selectin")
