from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.requisition import CentralStoreRequisition


class RequisitionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, requisition_id: int, for_update: bool = False):
        stmt = (
            select(CentralStoreRequisition)
            .options(selectinload(CentralStoreRequisition.lines))
            .where(CentralStoreRequisition.id == requisition_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, requesting_store_id: int | None = None, status: str | None = None):
        stmt = select(CentralStoreRequisition).options(
            selectinload(CentralStoreRequisition.lines)
        )
        if requesting_store_id is not None:
            stmt = stmt.where(CentralStoreRequisition.requesting_store_id == requesting_store_id)
        if status is not None:
            stmt = stmt.where(CentralStoreRequisition.status == status)
        stmt = stmt.order_by(CentralStoreRequisition.id.desc())
        return list((await self.session.scalars(stmt)).all())
