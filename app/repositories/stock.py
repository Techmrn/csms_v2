from datetime import date
from decimal import Decimal

from sqlalchemy import case, desc, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.category import Category
from app.models.item import Item
from app.models.stock import StockMovement
from app.models.unit import Unit


class StockRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def current_balance(self, store_id: int, financial_year_id: int, item_id: int) -> Decimal:
        item = await self.session.get(Item, item_id)
        if item:
            category = await self.session.get(Category, item.category_id)
            if category and category.type == "ASSET":
                cnt = await self.session.scalar(
                    select(func.count(Asset.id)).where(
                        Asset.current_store_id == store_id,
                        Asset.status == "IN_STOCK",
                        Asset.item_id == item_id,
                    )
                )
                return Decimal(cnt or 0)

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
        return await self.current_stock(store_id, financial_year_id, item_id)

    async def current_stock(
        self,
        store_id: int,
        financial_year_id: int,
        item_id: int | None = None,
    ) -> list[tuple]:
        balance_expr = func.coalesce(func.sum(StockMovement.quantity_in), 0) - func.coalesce(
            func.sum(StockMovement.quantity_out), 0
        )
        stmt_consumables = (
            select(
                StockMovement.store_id,
                StockMovement.financial_year_id,
                StockMovement.item_id,
                Item.code,
                Item.name,
                Unit.code.label("unit_code"),
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
            .having(balance_expr > 0)
        )
        stmt_assets = (
            select(
                literal(store_id).label("store_id"),
                literal(financial_year_id).label("financial_year_id"),
                Item.id.label("item_id"),
                Item.code,
                Item.name,
                Unit.code.label("unit_code"),
                func.count(Asset.id).label("balance"),
            )
            .join(Item, Item.id == Asset.item_id)
            .join(Unit, Unit.id == Item.unit_id)
            .where(
                Asset.current_store_id == store_id,
                Asset.status == "IN_STOCK",
            )
            .group_by(Item.id, Item.code, Item.name, Unit.code)
            .having(func.count(Asset.id) > 0)
        )
        if item_id is not None:
            stmt_consumables = stmt_consumables.where(StockMovement.item_id == item_id)
            stmt_assets = stmt_assets.where(Item.id == item_id)

        rows_c = list((await self.session.execute(stmt_consumables)).all())
        rows_a = list((await self.session.execute(stmt_assets)).all())
        combined = rows_c + rows_a
        combined.sort(key=lambda r: r.name)
        return combined

    async def all_item_balances(self, store_id: int, financial_year_id: int, search: str | None = None):
        """Return every active item for a store/FY, including zero-balance items and in-stock assets."""
        consumable_subquery = (
            select(
                StockMovement.item_id,
                (
                    func.coalesce(func.sum(StockMovement.quantity_in), 0)
                    - func.coalesce(func.sum(StockMovement.quantity_out), 0)
                ).label("consumable_balance"),
            )
            .where(
                StockMovement.store_id == store_id,
                StockMovement.financial_year_id == financial_year_id,
            )
            .group_by(StockMovement.item_id)
            .subquery()
        )

        asset_subquery = (
            select(
                Asset.item_id,
                func.count(Asset.id).label("asset_balance"),
            )
            .where(
                Asset.current_store_id == store_id,
                Asset.status == "IN_STOCK",
            )
            .group_by(Asset.item_id)
            .subquery()
        )

        balance_expr = case(
            (Category.type == "ASSET", func.coalesce(asset_subquery.c.asset_balance, 0)),
            else_=func.coalesce(consumable_subquery.c.consumable_balance, 0),
        )

        stmt = (
            select(
                Item.id.label("item_id"),
                Item.code.label("item_code"),
                Item.name.label("item_name"),
                Unit.code.label("unit_code"),
                balance_expr.label("balance"),
            )
            .join(Unit, Unit.id == Item.unit_id)
            .join(Category, Category.id == Item.category_id)
            .outerjoin(consumable_subquery, consumable_subquery.c.item_id == Item.id)
            .outerjoin(asset_subquery, asset_subquery.c.item_id == Item.id)
            .where(Item.is_active.is_(True))
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
