from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.stock_control import Adjustment, StockVerification, UnserviceableMaterial


class StockVerificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, verification_id: int, *, for_update: bool = False) -> StockVerification | None:
        stmt = (
            select(StockVerification)
            .options(selectinload(StockVerification.lines))
            .where(StockVerification.id == verification_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[StockVerification]:
        stmt = select(StockVerification).options(selectinload(StockVerification.lines)).order_by(StockVerification.id.desc())
        if store_id is not None:
            stmt = stmt.where(StockVerification.store_id == store_id)
        if status is not None:
            stmt = stmt.where(StockVerification.status == status)
        result = await self.session.scalars(stmt)
        return list(result.all())


class AdjustmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, adjustment_id: int, *, for_update: bool = False) -> Adjustment | None:
        stmt = (
            select(Adjustment)
            .options(selectinload(Adjustment.lines))
            .where(Adjustment.id == adjustment_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[Adjustment]:
        stmt = select(Adjustment).options(selectinload(Adjustment.lines)).order_by(Adjustment.id.desc())
        if store_id is not None:
            stmt = stmt.where(Adjustment.store_id == store_id)
        if status is not None:
            stmt = stmt.where(Adjustment.status == status)
        result = await self.session.scalars(stmt)
        return list(result.all())


class UnserviceableRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, record_id: int, *, for_update: bool = False) -> UnserviceableMaterial | None:
        stmt = (
            select(UnserviceableMaterial)
            .options(selectinload(UnserviceableMaterial.lines))
            .where(UnserviceableMaterial.id == record_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[UnserviceableMaterial]:
        stmt = select(UnserviceableMaterial).options(selectinload(UnserviceableMaterial.lines)).order_by(UnserviceableMaterial.id.desc())
        if store_id is not None:
            stmt = stmt.where(UnserviceableMaterial.store_id == store_id)
        if status is not None:
            stmt = stmt.where(UnserviceableMaterial.status == status)
        result = await self.session.scalars(stmt)
        return list(result.all())
