from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.office import Office
    from app.models.user import User


class Store(TimestampMixin, Base):
    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint(
            "store_type in ('CENTRAL', 'BRANCH', 'OTHER')",
            name="store_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    store_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    office: Mapped["Office"] = relationship(back_populates="stores")
    users: Mapped[list["User"]] = relationship(
        secondary="user_stores", back_populates="stores"
    )
