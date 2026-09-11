from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.stock_return import StockReturn


class StockReturnRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, return_id: int, *, for_update: bool = False) -> StockReturn | None:
        stmt = select(StockReturn).options(selectinload(StockReturn.lines)).where(StockReturn.id == return_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[StockReturn]:
        stmt = (
            select(StockReturn)
            .options(selectinload(StockReturn.lines))
            .order_by(StockReturn.return_date.desc(), StockReturn.id.desc())
        )
        if store_id is not None:
            stmt = stmt.where(StockReturn.store_id == store_id)
        if status is not None:
            stmt = stmt.where(StockReturn.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
