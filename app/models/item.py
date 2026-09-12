from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.unit import Unit


class Item(TimestampMixin, Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("name", "category_id", name="uq_items_name_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="RESTRICT"), nullable=False)
    specification: Mapped[str | None] = mapped_column(nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_temporary: Mapped[bool] = mapped_column(nullable=False, default=False)

    category: Mapped["Category"] = relationship()
    unit: Mapped["Unit"] = relationship()
