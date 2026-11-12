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
    from app.models.section import Section
    from app.models.store import Store
    from app.models.unit import Unit
    from app.models.user import User
    from app.paper_store.models.item import PaperItem


class PaperIndent(TimestampMixin, Base):
    __tablename__ = "paper_indents"
    __table_args__ = (
        CheckConstraint(
            "request_source in ('PHYSICAL', 'ONLINE')",
            name="ck_paper_indent_source_valid",
        ),
        CheckConstraint(
            "status in ('RECORDED', 'SUBMITTED', 'APPROVED', 'FINALIZED', 'REJECTED', 'CANCELLED')",
            name="ck_paper_indent_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    indent_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    indent_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    job_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_source: Mapped[str] = mapped_column(String(20), nullable=False, default="PHYSICAL")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="FINALIZED")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    store: Mapped["Store"] = relationship(lazy="selectin")
    section: Mapped["Section"] = relationship(lazy="selectin")
    financial_year: Mapped["FinancialYear"] = relationship(lazy="selectin")
    lines: Mapped[list["PaperIndentLine"]] = relationship(
        back_populates="indent", cascade="all, delete-orphan", lazy="selectin"
    )
    issue: Mapped["PaperIssue | None"] = relationship(back_populates="indent", uselist=False, lazy="selectin")


class PaperIndentLine(Base):
    __tablename__ = "paper_indent_lines"
    __table_args__ = (
        UniqueConstraint("indent_id", "paper_item_id", name="uq_paper_indent_lines_indent_item"),
        CheckConstraint(
            "requested_sheets > 0 OR requested_weight_kg > 0 OR requested_quantity > 0",
            name="ck_paper_indent_line_req_valid",
        ),
        CheckConstraint(
            "issued_quantity is null or issued_quantity >= 0",
            name="ck_paper_indent_line_iss_qty_nonneg",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    indent_id: Mapped[int] = mapped_column(
        ForeignKey("paper_indents.id", ondelete="CASCADE"), nullable=False
    )
    paper_item_id: Mapped[int] = mapped_column(
        ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    issued_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    requested_sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    approved_sheets: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issued_sheets: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    requested_weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    approved_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    issued_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    indent: Mapped[PaperIndent] = relationship(back_populates="lines")
    paper_item: Mapped["PaperItem"] = relationship(lazy="selectin")
    unit: Mapped["Unit"] = relationship(lazy="selectin")


class PaperIssue(TimestampMixin, Base):
    __tablename__ = "paper_issues"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    issue_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    financial_year_id: Mapped[int] = mapped_column(
        ForeignKey("financial_years.id", ondelete="RESTRICT"), nullable=False
    )
    indent_id: Mapped[int] = mapped_column(
        ForeignKey("paper_indents.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    job_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="FINALIZED")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posting_group_id: Mapped[UUID | None] = mapped_column(nullable=True)

    indent: Mapped[PaperIndent] = relationship(back_populates="issue", lazy="selectin")
    store: Mapped["Store"] = relationship(lazy="selectin")
    section: Mapped["Section"] = relationship(lazy="selectin")
    financial_year: Mapped["FinancialYear"] = relationship(lazy="selectin")
    poster: Mapped["User | None"] = relationship(foreign_keys=[posted_by], lazy="selectin")
    lines: Mapped[list["PaperIssueLine"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", lazy="selectin"
    )


class PaperIssueLine(Base):
    __tablename__ = "paper_issue_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_paper_issue_line_qty_nonneg"),
        CheckConstraint("weight_kg >= 0", name="ck_paper_issue_line_wt_nonneg"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("paper_issues.id", ondelete="CASCADE"), nullable=False
    )
    paper_item_id: Mapped[int] = mapped_column(
        ForeignKey("paper_items.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    sheets: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=Decimal("0"))
    remarks: Mapped[str | None] = mapped_column(String(255), nullable=True)

    issue: Mapped[PaperIssue] = relationship(back_populates="lines")
    paper_item: Mapped["PaperItem"] = relationship(lazy="selectin")
    unit: Mapped["Unit"] = relationship(lazy="selectin")

