from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.receipt import Receipt


class ReceiptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, receipt_id: int, *, for_update: bool = False) -> Receipt | None:
        stmt = select(Receipt).options(selectinload(Receipt.lines)).where(Receipt.id == receipt_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[Receipt]:
        stmt = (
            select(Receipt)
            .options(selectinload(Receipt.lines))
            .order_by(Receipt.receipt_date.desc(), Receipt.id.desc())
        )
        if store_id is not None:
            stmt = stmt.where(Receipt.store_id == store_id)
        if status is not None:
            stmt = stmt.where(Receipt.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
