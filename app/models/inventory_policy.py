from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UserAuditMixin

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.store import Store
    from app.models.user import User


class InventoryPolicy(TimestampMixin, UserAuditMixin, Base):
    __tablename__ = "inventory_policies"
    __table_args__ = (
        UniqueConstraint("store_id", "item_id", name="uq_inventory_policy_store_item"),
        CheckConstraint("reorder_level is null or reorder_level >= 0", name="reorder_level_valid"),
        CheckConstraint("reorder_quantity is null or reorder_quantity > 0", name="reorder_quantity_valid"),
        CheckConstraint("maximum_stock_level is null or maximum_stock_level >= 0", name="maximum_stock_level_valid"),
        CheckConstraint("low_stock_level is null or low_stock_level >= 0", name="low_stock_level_valid"),
        CheckConstraint(
            "issue_method is null or issue_method in ('NONE', 'FIFO', 'LIFO', 'FEFO')",
            name="issue_method_valid",
        ),
        CheckConstraint("expiry_alert_days is null or expiry_alert_days >= 0", name="expiry_alert_days_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    reorder_level: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    reorder_quantity: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    maximum_stock_level: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    low_stock_level: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    issue_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    batch_tracking: Mapped[bool] = mapped_column(nullable=False, default=False)
    expiry_tracking: Mapped[bool] = mapped_column(nullable=False, default=False)
    expiry_alert_days: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    store: Mapped["Store"] = relationship()
    item: Mapped["Item"] = relationship()
