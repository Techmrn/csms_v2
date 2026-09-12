from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.petty_purchase import PettyPurchase


class PettyPurchaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, petty_purchase_id: int, *, for_update: bool = False) -> PettyPurchase | None:
        stmt = (
            select(PettyPurchase)
            .options(selectinload(PettyPurchase.lines))
            .where(PettyPurchase.id == petty_purchase_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[PettyPurchase]:
        stmt = select(PettyPurchase).options(selectinload(PettyPurchase.lines)).order_by(PettyPurchase.id.desc())
        if store_id is not None:
            stmt = stmt.where(PettyPurchase.store_id == store_id)
        if status is not None:
            stmt = stmt.where(PettyPurchase.status == status)
        result = await self.session.scalars(stmt)
        return list(result.all())
