from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset


class AssetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, asset_id: int) -> Asset | None:
        result = await self.session.execute(
            select(Asset)
            .options(selectinload(Asset.detail), selectinload(Asset.movements))
            .where(Asset.id == asset_id)
        )
        return result.scalar_one_or_none()

    async def get_by_asset_no(self, asset_no: str) -> Asset | None:
        return await self.session.scalar(select(Asset).where(Asset.asset_no == asset_no))

    async def list(
        self,
        store_id: int | None = None,
        office_id: int | None = None,
        status: str | None = None,
        item_id: int | None = None,
        allowed_store_ids: list[int] | None = None,
    ) -> list[Asset]:
        stmt = select(Asset).options(selectinload(Asset.detail))
        if store_id is not None:
            stmt = stmt.where(Asset.current_store_id == store_id)
        elif allowed_store_ids is not None:
            stmt = stmt.where(Asset.current_store_id.in_(allowed_store_ids))
        if office_id is not None:
            stmt = stmt.where(Asset.current_office_id == office_id)
        if status is not None:
            stmt = stmt.where(Asset.status == status)
        if item_id is not None:
            stmt = stmt.where(Asset.item_id == item_id)
        result = await self.session.execute(stmt.order_by(Asset.asset_no))
        return list(result.scalars().all())
