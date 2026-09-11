from datetime import date

from sqlalchemy import CheckConstraint, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import TimestampMixin


class FinancialYear(TimestampMixin, Base):
    __tablename__ = "financial_years"
    __table_args__ = (
        CheckConstraint("start_date < end_date", name="financial_year_dates_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year_name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_closed: Mapped[bool] = mapped_column(nullable=False, default=False)
