from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.section import Section
    from app.models.store import Store
    from app.models.user import User


class Office(TimestampMixin, Base):
    __tablename__ = "offices"
    __table_args__ = (
        CheckConstraint(
            "office_type in ('DIRECTORATE', 'BRANCH', 'OTHER')",
            name="office_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    office_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_office_id: Mapped[int | None] = mapped_column(
        ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True
    )
    display_order: Mapped[int | None] = mapped_column(nullable=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    parent: Mapped["Office | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Office"]] = relationship(back_populates="parent")
    sections: Mapped[list["Section"]] = relationship(back_populates="office")
    stores: Mapped[list["Store"]] = relationship(back_populates="office")
    users: Mapped[list["User"]] = relationship(back_populates="office", foreign_keys="User.office_id")
