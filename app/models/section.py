from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.office import Office
    from app.models.user import User


class Section(TimestampMixin, Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("office_id", "code", name="uq_sections_office_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    office: Mapped["Office"] = relationship(back_populates="sections")
    users: Mapped[list["User"]] = relationship(back_populates="section", foreign_keys="User.section_id")
