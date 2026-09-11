from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin

if TYPE_CHECKING:
    from app.models.office import Office
    from app.models.permission import Permission
    from app.models.role import Role
    from app.models.section import Section
    from app.models.store import Store


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

user_stores = Table(
    "user_stores",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("store_id", ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True),
    Column("is_primary", nullable=False, default=False),
)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    office_id: Mapped[int | None] = mapped_column(ForeignKey("offices.id", ondelete="RESTRICT"), nullable=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    remarks: Mapped[str | None] = mapped_column(nullable=True)

    office: Mapped["Office | None"] = relationship(
        back_populates="users", foreign_keys=[office_id]
    )
    section: Mapped["Section | None"] = relationship(
        back_populates="users", foreign_keys=[section_id]
    )
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users")
    stores: Mapped[list["Store"]] = relationship(secondary=user_stores, back_populates="users")
