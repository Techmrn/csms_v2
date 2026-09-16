from datetime import date
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.stock import StockMovement
from app.models.unit import Unit


class StockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def current_balance(self, store_id: int, financial_year_id: int, item_id: int) -> Decimal:
        result = await self.session.scalar(
            select(
                func.coalesce(func.sum(StockMovement.quantity_in), 0)
                - func.coalesce(func.sum(StockMovement.quantity_out), 0)
            ).where(
                StockMovement.store_id == store_id,
                StockMovement.financial_year_id == financial_year_id,
                StockMovement.item_id == item_id,
            )
        )
        return Decimal(result or 0)

    async def balances(
        self,
        store_id: int,
        financial_year_id: int,
        item_id: int | None = None,
    ) -> list[tuple]:
        balance_expr = func.coalesce(func.sum(StockMovement.quantity_in), 0) - func.coalesce(
            func.sum(StockMovement.quantity_out), 0
        )
        stmt = (
            select(
                StockMovement.store_id,
                StockMovement.financial_year_id,
                StockMovement.item_id,
                Item.code,
                Item.name,
                Unit.code,
                balance_expr.label("balance"),
            )
            .join(Item, Item.id == StockMovement.item_id)
            .join(Unit, Unit.id == Item.unit_id)
            .where(
                StockMovement.store_id == store_id,
                StockMovement.financial_year_id == financial_year_id,
            )
            .group_by(
                StockMovement.store_id,
                StockMovement.financial_year_id,
                StockMovement.item_id,
                Item.code,
                Item.name,
                Unit.code,
            )
        )
        if item_id is not None:
            stmt = stmt.where(StockMovement.item_id == item_id)
        stmt = stmt.order_by(Item.name)
        rows = (await self.session.execute(stmt)).all()
        return list(rows)

    async def all_item_balances(self, store_id: int, financial_year_id: int, search: str | None = None):
        """Return every active item for a store/FY, including zero-balance items."""
        movement_balance = func.coalesce(func.sum(StockMovement.quantity_in), 0) - func.coalesce(
            func.sum(StockMovement.quantity_out), 0
        )
        stmt = (
            select(
                Item.id.label("item_id"), Item.code.label("item_code"), Item.name.label("item_name"),
                Unit.code.label("unit_code"), movement_balance.label("balance"),
            )
            .join(Unit, Unit.id == Item.unit_id)
            .outerjoin(StockMovement, (StockMovement.item_id == Item.id) &
                       (StockMovement.store_id == store_id) &
                       (StockMovement.financial_year_id == financial_year_id))
            .where(Item.is_active.is_(True))
            .group_by(Item.id, Item.code, Item.name, Unit.code)
        )
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(Item.code.ilike(term) | Item.name.ilike(term))
        stmt = stmt.order_by(Item.name, Item.code)
        return list((await self.session.execute(stmt)).all())

    async def register(
        self,
        store_id: int,
        financial_year_id: int,
        item_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[dict]:
        running_balance = func.sum(
            StockMovement.quantity_in - StockMovement.quantity_out
        ).over(
            partition_by=[StockMovement.store_id, StockMovement.financial_year_id, StockMovement.item_id],
            order_by=[StockMovement.movement_date, StockMovement.id],
            rows=(None, 0),
        )
        stmt = select(
            StockMovement.id,
            StockMovement.movement_date,
            StockMovement.movement_type,
            StockMovement.quantity_in,
            StockMovement.quantity_out,
            running_balance.label("balance"),
            StockMovement.reference_type,
            StockMovement.reference_id,
            StockMovement.reference_no,
        ).where(
            StockMovement.store_id == store_id,
            StockMovement.financial_year_id == financial_year_id,
            StockMovement.item_id == item_id,
        )
        if from_date is not None:
            stmt = stmt.where(StockMovement.movement_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(StockMovement.movement_date <= to_date)
        stmt = stmt.order_by(StockMovement.movement_date, StockMovement.id)
        result = await self.session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def opening_already_posted(
        self, store_id: int, financial_year_id: int, item_id: int
    ) -> bool:
        movement = await self.session.scalar(
            select(StockMovement.id)
            .where(
                StockMovement.store_id == store_id,
                StockMovement.financial_year_id == financial_year_id,
                StockMovement.item_id == item_id,
                StockMovement.movement_type == "OPENING",
            )
            .limit(1)
        )
        return movement is not None
