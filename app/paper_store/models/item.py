from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.unit import Unit


class PaperItem(TimestampMixin, Base):
    __tablename__ = "paper_items"
    __table_args__ = (
        CheckConstraint(
            "form_type in ('SHEET', 'REEL')",
            name="ck_paper_items_form_type_valid",
        ),
        CheckConstraint("gsm > 0", name="ck_paper_items_gsm_positive"),
        CheckConstraint("sheets_per_ream > 0", name="ck_paper_items_sheets_per_ream_positive"),
        UniqueConstraint("name", "gsm", "form_type", name="uq_paper_items_name_gsm_form"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    paper_type: Mapped[str] = mapped_column(String(100), nullable=False)
    form_type: Mapped[str] = mapped_column(String(20), nullable=False)
    gsm: Mapped[int] = mapped_column(nullable=False)
    sheets_per_ream: Mapped[int] = mapped_column(nullable=False, default=500)
    length_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    width_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    reel_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    weight_per_ream_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    unit: Mapped["Unit"] = relationship()

